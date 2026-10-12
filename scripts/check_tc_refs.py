#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
用例编号引用反向校验：用例文档 ↔ 测试源码 双向 diff。

唯一键是「用例文件名 + 编号」，不用内容指纹生成 ID —— 指纹含标题正文与层级名，
文档一重排就全量换号，下游引用集体失效。

检查四项：
  1. 悬空引用   测试引用了用例文档里不存在的编号      → 门禁失败
  2. 裸号引用   引用没带文件名（编号跨文件会重复）        → 分级告警
  3. 疑似虚报   编号只在注释里声称、没对应用例名声明     → 告警
  4. 未覆盖     用例文档里的编号没有任何测试引用        → 统计

跟语言/框架无关：编号前缀、用例名标记、文档后缀、否定词均可参数化。

用法:
  python check_tc_refs.py --docs <用例目录> --tests <测试源码目录>
  python check_tc_refs.py --docs docs/cases --tests src/test --quiet
  python check_tc_refs.py --docs docs/cases --tests src/test --out report.txt

常见适配:
  编号不是 TC-     → --tc-prefix CASE-
  编号不是 4 位    → --tc-width 3
  不是 JUnit5      → --test-marker "def test_"（pytest）/ "it("（jest）/ "func Test"（go）
  用例不是 md      → --doc-glob "*.markdown"
  非中文项目        → --negation-pattern "not covered|uncovered|N/A"

Windows PowerShell 下管道会按控制台代码页解码导致中文乱码，两种解法：
  1) 先执行 [Console]::OutputEncoding = [System.Text.Encoding]::UTF8
  2) 用 --out 写到 UTF-8 文件再看

退出码: 0 = 无悬空引用；1 = 有悬空引用或裸号指向不存在的用例（门禁失败）；2 = 参数或读取错误
"""

import argparse
import re
import sys
from pathlib import Path

# ---- 可配置模式（由 configure() 根据命令行参数生成）----
TC_PREFIX = 'TC-'
TC_WIDTH = 4
TEST_MARKER = '@DisplayName'
DOC_GLOB = '*.md'

RE_MD_TC = None       # 用例文档里的编号标题
RE_REF_TAIL = None    # 引用的区间/列举尾部
RE_BARE = None        # 裸编号

# 同行出现这些词，说明是「明确声明不覆盖」，不算虚报也不算覆盖。
# 用 未.{0,3}覆盖 而不是 未覆盖，否则「未被覆盖」「未完全覆盖」会漏匹配，
# 把声明缺口的引用错算成真覆盖。非中文项目用 --negation-pattern 覆盖。
RE_NEGATION = re.compile(
    r'未.{0,3}覆盖|不.{0,3}覆盖|尚未|不在本|属前端|待补|无法|不可测|已归入|不计入')

COMMENT_PREFIXES = ('*', '//', '/*', '#', '--', ';')


def configure(tc_prefix, tc_width, test_marker, doc_glob, negation_pattern):
    """按项目实际约定生成全部正则。"""
    global TC_PREFIX, TC_WIDTH, TEST_MARKER, DOC_GLOB, RE_NEGATION
    global RE_MD_TC, RE_REF_TAIL, RE_BARE
    TC_PREFIX, TC_WIDTH = tc_prefix, tc_width
    TEST_MARKER, DOC_GLOB = test_marker, doc_glob
    if negation_pattern:
        RE_NEGATION = re.compile(negation_pattern)
    p = re.escape(tc_prefix)
    RE_MD_TC = re.compile(r'^#{1,6}\s*%s(\d+)' % p, re.MULTILINE)
    RE_REF_TAIL = re.compile(r'\s*([~/])\s*(?:%s)?(\d+)' % p)
    # 裸编号 = 前面不是 '#' 的编号（带文件名的引用形式为 文件.md#TC-0008）
    RE_BARE = re.compile(r'(?<!#)\b%s(\d+)' % p)


def build_ref_regex(doc_names):
    """用实际存在的用例文件名构造引用正则。

    不能用「任意非空白字符 + 后缀」去捕文件名：用例名注解里常写成
    「中文说明；某文件.md#TC-0008」，而中文全角标点（；、（）不在排除集里，
    会被贪婪地当成文件名的一部分，产生大量假的悬空引用。
    按已知文件名建 alternation 从根上消除这类误报；长的排前面，避免短名先命中。
    """
    alternation = '|'.join(re.escape(name)
                           for name in sorted(doc_names, key=len, reverse=True))
    p = re.escape(TC_PREFIX)
    return re.compile(r'(%s)#%s(\d+)((?:\s*[~/]\s*(?:%s)?\d+)*)' % (alternation, p, p))


def expand_ref(tc_first, tail):
    """把 '0038' + ' ~ 0041' 展开成编号列表。'/' 视为列举，'~' 视为区间。"""
    first = int(tc_first)
    numbers = [first]
    for sep, num in RE_REF_TAIL.findall(tail or ''):
        n = int(num)
        if sep == '/':
            numbers.append(n)
        else:
            lo, hi = min(first, n), max(first, n)
            numbers.extend(range(lo, hi + 1))
    # 区间展开后要去重并保持有序
    return sorted(set(numbers))


def fmt_tc(n):
    return '%s%0*d' % (TC_PREFIX, TC_WIDTH, n)


def load_docs(docs_dir):
    """返回 {用例文件名: set(编号)}，只收含编号标题的文件。"""
    result = {}
    for path in sorted(docs_dir.rglob(DOC_GLOB)):
        try:
            text = path.read_text(encoding='utf-8')
        except (UnicodeDecodeError, OSError) as exc:
            print('[WARN] 跳过无法读取的文件 %s: %s' % (path, exc))
            continue
        numbers = {int(m) for m in RE_MD_TC.findall(text)}
        if numbers:
            result[path.name] = numbers
    return result


def is_comment_line(line):
    stripped = line.strip()
    return stripped.startswith(COMMENT_PREFIXES)


def is_displayname_line(line):
    return TEST_MARKER in line


def load_refs(tests_dir, docs):
    """扫描测试源码，返回 (带文件名引用, 声明不覆盖的引用, 裸号引用, 疑似虚报, 文件→md)。"""
    re_ref = build_ref_regex(docs.keys())
    qualified = {}   # (md名, TC号) -> [(文件, 行号)]
    disclaimed = {}  # (md名, TC号) -> [(文件, 行号)]；同行含「未覆盖」类措辞，不计入覆盖
    bare = {}        # TC号 -> {(文件, 行号)}
    suspected = {}   # (md名, TC号) -> (文件, 行号)
    file_to_docs = {}  # 测试文件 -> 它引用过的 md 名集合

    for path in sorted(tests_dir.rglob('*')):
        if not path.is_file() or path.suffix.lower() in ('.class', '.jar', '.png', '.xlsx'):
            continue
        try:
            lines = path.read_text(encoding='utf-8').splitlines()
        except (UnicodeDecodeError, OSError):
            continue

        seen_in_displayname = set()
        seen_in_comment = {}

        for lineno, line in enumerate(lines, start=1):
            for md_name, tc_first, tail in re_ref.findall(line):
                file_to_docs.setdefault(path, set()).add(md_name)
                # 同行写了「未覆盖/不覆盖/属前端」等，说明是声明缺口而不是提供覆盖
                target = disclaimed if RE_NEGATION.search(line) else qualified
                for n in expand_ref(tc_first, tail):
                    key = (md_name, n)
                    target.setdefault(key, []).append((path, lineno))
                    if target is qualified:
                        if is_displayname_line(line):
                            seen_in_displayname.add(key)
                        elif is_comment_line(line):
                            seen_in_comment.setdefault(key, (path, lineno))

            # 裸号：只统计出现在用例名声明行的（注释里提编号属正常说明）
            if is_displayname_line(line):
                for m in RE_BARE.finditer(line):
                    bare.setdefault(int(m.group(1)), set()).add((path, lineno))

        for key, where in seen_in_comment.items():
            if key in seen_in_displayname:
                continue
            # 同一行有「不覆盖」类措辞的，是诚实声明，不算虚报
            line_text = lines[where[1] - 1]
            if RE_NEGATION.search(line_text):
                continue
            suspected[key] = where

    return qualified, disclaimed, bare, suspected, file_to_docs


def main():
    parser = argparse.ArgumentParser(description='用例编号引用反向校验')
    parser.add_argument('--docs', required=True, help='用例文档所在目录')
    parser.add_argument('--tests', required=True, help='测试源码所在目录')
    parser.add_argument('--quiet', action='store_true', help='只输出问题与汇总，不列明细')
    parser.add_argument('--out', help='把报告写入指定 UTF-8 文件（规避控制台编码问题）')
    parser.add_argument('--tc-prefix', default='TC-', help='编号前缀，默认 TC-')
    parser.add_argument('--tc-width', type=int, default=4, help='编号补零位数，默认 4')
    parser.add_argument('--test-marker', default='@DisplayName',
                        help='用例名声明行的标记，默认 @DisplayName（JUnit5）；'
                             'pytest 用 "def test_"，jest 用 "it("，go 用 "func Test"')
    parser.add_argument('--doc-glob', default='*.md', help='用例文档文件名模式，默认 *.md')
    parser.add_argument('--negation-pattern', default=None,
                        help='「声明不覆盖」的正则，默认中文词表；非中文项目必须显式传')
    args = parser.parse_args()

    configure(args.tc_prefix, args.tc_width, args.test_marker, args.doc_glob,
              args.negation_pattern)

    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    if args.out:
        # 同时写文件与控制台：控制台可能乱码，文件一定是 UTF-8
        import io
        tee = open(args.out, 'w', encoding='utf-8', newline='\n')
        real_stdout = sys.stdout

        class _Tee(io.TextIOBase):
            def write(self, text):
                tee.write(text)
                real_stdout.write(text)
                return len(text)

            def flush(self):
                tee.flush()
                real_stdout.flush()

        sys.stdout = _Tee()

    docs_dir, tests_dir = Path(args.docs), Path(args.tests)
    if not docs_dir.is_dir():
        print('[ERROR] 用例目录不存在: %s' % docs_dir)
        return 2
    if not tests_dir.is_dir():
        print('[ERROR] 测试目录不存在: %s' % tests_dir)
        return 2

    docs = load_docs(docs_dir)
    if not docs:
        print('[ERROR] %s 下按 %s 没找到任何含 %s编号标题的文档'
              % (docs_dir, args.doc_glob, args.tc_prefix))
        return 2

    qualified, disclaimed, bare, suspected, file_to_docs = load_refs(tests_dir, docs)

    all_tcs = {(name, n) for name, numbers in docs.items() for n in numbers}
    # 悬空校验对两类引用都要做：声明不覆盖也不能引一个不存在的 TC 号
    dangling = sorted(k for k in qualified if k not in all_tcs)
    dangling += sorted(k for k in disclaimed if k not in all_tcs)
    covered = sorted(k for k in qualified if k in all_tcs)
    uncovered = sorted(all_tcs - set(qualified) - set(disclaimed))
    gaps = sorted(k for k in disclaimed if k in all_tcs)

    print('=' * 68)
    print('用例编号引用反向校验')
    print('=' * 68)
    print('配置: 编号前缀=%s 位数=%d 用例名标记=%r 文档模式=%s'
          % (args.tc_prefix, args.tc_width, args.test_marker, args.doc_glob))
    print('用例文档: %d 份，编号总数 %d' % (len(docs), len(all_tcs)))
    for name in sorted(docs):
        hit = sum(1 for k in covered if k[0] == name)
        total = len(docs[name])
        print('  %-42s %3d / %3d  %5.1f%%' % (name, hit, total, 100.0 * hit / total))
    print('测试引用到的编号（真覆盖）: %d 条' % len(covered))
    print('代码里显式声明「不覆盖」的编号: %d 条' % len(gaps))
    if gaps and not args.quiet:
        for md_name, n in gaps:
            for path, lineno in disclaimed[(md_name, n)]:
                print('  ⚪ %s:%d  %s#%s' % (path, lineno, md_name, fmt_tc(n)))
    print()

    fail = False

    print('【1】悬空引用（测试引了用例文档里不存在的编号）: %d' % len(dangling))
    if dangling:
        fail = True
        for md_name, n in dangling:
            for path, lineno in qualified[(md_name, n)]:
                print('  🔴 %s:%d  %s#%s' % (path, lineno, md_name, fmt_tc(n)))
            exists_elsewhere = [name for name in docs if n in docs[name]]
            if exists_elsewhere:
                print('     ↳ 该编号存在于: %s（文件名写错了？）' % ', '.join(exists_elsewhere))
    print()

    bare_ambiguous = []   # 该 TC 号在本文件引用的多份 md 里都存在 → 真的无法定位
    bare_dangling = []    # 该 TC 号在本文件引用的任何 md 里都不存在 → 指向了不存在的用例
    bare_single = []      # 能唯一推断出归属，但未写文件名，仅违反约定
    bare_noanchor = []    # 本文件从未用过「文件名#TC-」格式，无法判定归属
    for n in sorted(bare):
        for path, lineno in sorted(bare[n]):
            referenced = file_to_docs.get(path)
            if not referenced:
                bare_noanchor.append((path, lineno, n))
                continue
            owners = sorted(d for d in referenced if n in docs.get(d, ()))
            if len(owners) >= 2:
                bare_ambiguous.append((path, lineno, n, owners))
            elif len(owners) == 1:
                bare_single.append((path, lineno, n))
            else:
                bare_dangling.append((path, lineno, n))

    print('【2】裸号引用（用例名里没带文件名）: 真歧义 %d / 指向不存在 %d / 可推断 %d / 无锚点 %d'
          % (len(bare_ambiguous), len(bare_dangling), len(bare_single), len(bare_noanchor)))
    if bare_ambiguous:
        print('  🔴 真歧义：该编号在本文件引用的多份文档里都存在，无法判定指哪一条')
        for path, lineno, n, owners in bare_ambiguous:
            print('     %s:%d  %s  （同时存在于: %s）' % (path, lineno, fmt_tc(n), ', '.join(owners)))
    if bare_dangling:
        fail = True
        print('  🔴 指向不存在：本文件引用的文档里都没有这个编号')
        for path, lineno, n in bare_dangling:
            print('     %s:%d  %s' % (path, lineno, fmt_tc(n)))
    if bare_noanchor and not args.quiet:
        print('  🟠 无锚点：本文件从未用过「文件名#编号」格式，裸号无法回溯到具体用例文档')
        for path, lineno, n in bare_noanchor:
            print('     %s:%d  %s' % (path, lineno, fmt_tc(n)))
    if bare_single and not args.quiet:
        print('  🟡 可推断：归属唯一，但仍建议补全文件名以符合约定')
        for path, lineno, n in bare_single:
            print('     %s:%d  %s' % (path, lineno, fmt_tc(n)))
    print()

    print('【3】疑似虚报覆盖（只在注释里声称，无用例名声明）: %d' % len(suspected))
    if suspected:
        for (md_name, n), (path, lineno) in sorted(suspected.items()):
            print('  🟠 %s:%d  %s#%s' % (path, lineno, md_name, fmt_tc(n)))
        print('     ↳ 启发式判定，需人工确认：要么补测试，要么把声称删掉')
    print()

    print('【4】未覆盖编号（既无测试也无显式声明）: %d' % len(uncovered))
    if uncovered and not args.quiet:
        current = None
        for md_name, n in uncovered:
            if md_name != current:
                print('  %s' % md_name)
                current = md_name
            print('    %s' % fmt_tc(n), end='')
        print()
    print()

    print('=' * 68)
    if fail:
        print('结果: FAIL —— 存在悬空引用或裸号指向不存在的用例，门禁不通过')
        return 1
    print('结果: PASS —— 无悬空引用（无锚点 %d 处、可推断裸号 %d 处、疑似虚报 %d 处需人工确认）'
          % (len(bare_noanchor), len(bare_single), len(suspected)))
    return 0


if __name__ == '__main__':
    sys.exit(main())
