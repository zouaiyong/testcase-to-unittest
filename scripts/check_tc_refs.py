#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
用例编号引用反向校验：用例文档 ↔ 测试源码 双向 diff，可选再与覆盖矩阵对账。

唯一键是「用例文件名 + 编号」，不用内容指纹生成 ID —— 指纹含标题正文与层级名，
文档一重排就全量换号，下游引用集体失效。

用例文档认两种格式（即 testcase-design 的两种产物）：
  - Markdown：编号写在标题开头（# ~ ###### TC-0001 ...）
  - CSV：编号写在「用例编号」列（没有该列时取第 1 列），可带 BOM

检查五项：
  1. 悬空引用   测试引用了用例文档里不存在的编号      → 门禁失败
  2. 裸号引用   引用没带文件名（编号跨文件会重复）        → 分级告警
  3. 疑似虚报   编号只在注释里声称、没对应用例名声明     → 告警
  4. 未覆盖     用例文档里的编号没有任何测试引用        → 统计
  5. 矩阵对账   传了 --matrix 才做：A 虚报已写 / B 漏登 / C 零归属 → 门禁失败；D 逐条方法数 → 咨询

跟语言/框架无关：编号前缀、用例名标记、测试方法声明、文档后缀、否定词均可参数化。

用法:
  python check_tc_refs.py --docs <用例目录> --tests <测试源码目录>
  python check_tc_refs.py --docs testcases --tests src/test --matrix testcases/自动化覆盖矩阵.md
  python check_tc_refs.py --docs docs/cases --tests src/test --quiet
  python check_tc_refs.py --docs docs/cases --tests src/test --out report.txt
  python check_tc_refs.py --selftest

常见适配:
  编号不是 TC-     → --tc-prefix CASE-
  编号不是 4 位    → --tc-width 3
  不是 JUnit5      → --test-marker "def test_"（pytest）/ "it("（jest）/ "func Test"（go），
                     并配 --test-annotation-pattern（见 --help）
  文档后缀不同      → --doc-glob "*.markdown,*.csv"（逗号分隔多个模式）
  非中文项目        → --negation-pattern "not covered|uncovered|N/A"

Windows PowerShell 下管道会按控制台代码页解码导致中文乱码，两种解法：
  1) 先执行 [Console]::OutputEncoding = [System.Text.Encoding]::UTF8
  2) 用 --out 写到 UTF-8 文件再看

退出码: 0 = 门禁通过；1 = 门禁失败（悬空引用、裸号指向不存在的用例、矩阵对账 A/B/C 或归属总账不自洽）；
        2 = 参数或读取错误
"""

import argparse
import csv
import io
import re
import sys
from pathlib import Path

# ---- 可配置模式（由 configure() 根据命令行参数生成）----
TC_PREFIX = 'TC-'
TC_WIDTH = 4
TEST_MARKER = '@DisplayName'
DOC_GLOB = '*.md,*.csv'

RE_MD_TC = None       # Markdown 用例里的编号标题
RE_CSV_TC = None      # CSV 用例编号列里的单元格
RE_REF_TAIL = None    # 引用的区间/列举尾部
RE_BARE = None        # 裸编号

# 同行出现这些词，说明是「明确声明不覆盖」，不算虚报也不算覆盖。
# 用 未.{0,3}覆盖 而不是 未覆盖，否则「未被覆盖」「未完全覆盖」会漏匹配，
# 把声明缺口的引用错算成真覆盖。非中文项目用 --negation-pattern 覆盖。
RE_NEGATION = re.compile(
    r'未.{0,3}覆盖|不.{0,3}覆盖|尚未|不在本|属前端|待补|无法|不可测|已归入|不计入')

COMMENT_PREFIXES = ('*', '//', '/*', '#', '--', ';')

# 类/分组声明行。用于判定一个用例名标记到底是「方法自己的」还是「类级的」：
# 若标记行与测试注解之间隔着类声明，则该标记属于类，不能被第一个方法领走。
RE_CLASS_DECL = re.compile(
    r'^\s*(?:public\s+|private\s+|protected\s+|static\s+|final\s+|abstract\s+'
    r'|inner\s+|open\s+|data\s+)*(?:class|interface|object)\s+\w+|^\s*describe\s*\(')


def configure(tc_prefix, tc_width, test_marker, doc_glob, negation_pattern):
    """按项目实际约定生成全部正则。"""
    global TC_PREFIX, TC_WIDTH, TEST_MARKER, DOC_GLOB, RE_NEGATION
    global RE_MD_TC, RE_CSV_TC, RE_REF_TAIL, RE_BARE
    TC_PREFIX, TC_WIDTH = tc_prefix, tc_width
    TEST_MARKER, DOC_GLOB = test_marker, doc_glob
    if negation_pattern:
        RE_NEGATION = re.compile(negation_pattern)
    p = re.escape(tc_prefix)
    RE_MD_TC = re.compile(r'^#{1,6}\s*%s(\d+)' % p, re.MULTILINE)
    RE_CSV_TC = re.compile(r'^\s*%s(\d+)\s*$' % p)
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
    """把 '0038' + ' ~ 0041' 展开成编号列表。'/' 视为列举，'~' 视为区间。

    区间的起点是**前一个编号**而不是首个编号：否则 '0031/0032/0034~0037'
    会被展开成 31..37，把特意排除在外的 0033 也括进来。
    """
    first = int(tc_first)
    numbers = [first]
    prev = first
    for sep, num in RE_REF_TAIL.findall(tail or ''):
        n = int(num)
        if sep == '/':
            numbers.append(n)
        else:
            lo, hi = min(prev, n), max(prev, n)
            numbers.extend(range(lo, hi + 1))
        prev = n
    # 区间展开后要去重并保持有序
    return sorted(set(numbers))


def _cells_of(line):
    return [c.strip() for c in line.strip().strip('|').split('|')]


def _is_separator(line):
    """判定 Markdown 表格的分隔行（如 |---|:--:|---:|）。

    先 join 再取字符集：单元格是 '---' 这样的多字符串，
    直接 set(cells) 得到的是 {'---'} 而不是 {'-'}，会判不出分隔行。
    """
    if not line.lstrip().startswith('|'):
        return False
    joined = ''.join(_cells_of(line))
    return bool(joined) and set(joined) <= set('-: ')


def _selftest():
    """回归用例：编号展开（混合列举+区间）、分隔行（多字符单元格）、
    CSV 编号列、方法归属（独占与同行标记）——这几处最容易改坏。"""
    configure('TC-', 4, '@DisplayName', '*.md,*.csv', None)
    cases = [
        (('0038', ''), [38]),
        (('0038', ' ~ 0041'), [38, 39, 40, 41]),
        (('0038', '~0041'), [38, 39, 40, 41]),
        (('0007', '/0009'), [7, 9]),
        (('0031', '/0032/0034~0037'), [31, 32, 34, 35, 36, 37]),
        (('0041', '~0038'), [38, 39, 40, 41]),
        (('0015', '/0016/0018'), [15, 16, 18]),
    ]
    bad = [('expand_ref%r' % (args,), got, want) for args, want in cases
           for got in [expand_ref(*args)] if got != want]

    # 分隔行判定：单元格是多字符时仍要认得，但不能把空表格行误判成分隔行
    import tempfile
    sep_cases = [
        ('|---|---|', True),
        ('| --- | :---: | ---: |', True),
        ('| 用例引用 | 预期方法数 | 状态 |', False),
        ('| a.md#TC-0001 | 3 | 已写 |', False),
    ]
    with tempfile.TemporaryDirectory() as td:
        mp = Path(td) / 'm.md'
        for text, want in sep_cases:
            mp.write_text('| 预期方法数 | 状态 |\n%s\n' % text, encoding='utf-8')
            src = mp.read_text(encoding='utf-8').splitlines()
            got = _is_separator(src[1])
            if got != want:
                bad.append(('_is_separator(%r)' % text, got, want))

    # CSV：只认编号列，预期结果里顺带提到的编号不算；单元格可以跨行
    csv_text = ('用例编号,用例标题,预期结果\n'
                'TC-0001,注册,"1. 注册成功\n2. 创建账号"\n'
                'TC-0002,拦截,"1. 拦截口径同 TC-0009"\n')
    got = sorted(_csv_numbers(csv_text))
    if got != [1, 2]:
        bad.append(('_csv_numbers', got, [1, 2]))

    # 方法归属：没写标记的方法不能领走邻居的标记；与声明同行的标记归该方法自己
    java = ('class T {\n'
            '    @Test\n'
            '    @DisplayName("a.md#TC-0001 x")\n'
            '    void x() {}\n'
            '    @Test\n'
            '    void implOnly() {}\n'
            '}\n')
    jest = ("describe('g', () => {\n"
            "  it('a.md#TC-0001 x', () => {\n"
            "  });\n"
            "  it('a.md#TC-0001 y', () => {\n"
            "  });\n"
            "  it('a.md#TC-0002 z', () => {\n"
            "  });\n"
            "});\n")
    docs = {'a.md': {1, 2}}
    for marker, anno, name, text, want in [
            ('@DisplayName', r'^\s*@Test\b', 'T.java', java, ({1: 1.0}, 1)),
            ('it(', r'^\s*(it|test)\(', 't.test.js', jest, ({1: 2.0, 2: 1.0}, 0))]:
        configure('TC-', 4, marker, '*.md,*.csv', None)
        with tempfile.TemporaryDirectory() as td:
            (Path(td) / name).write_text(text, encoding='utf-8')
            _total, per_tc, unattributed, _shared = scan_methods(
                Path(td), docs, build_ref_regex(docs), re.compile(anno))
        got = ({n: round(v, 2) for (_md, n), v in per_tc.items()}, len(unattributed))
        if got != want:
            bad.append(('scan_methods(%s) -> (归属, 无法归属数)' % name, got, want))
    return bad


def fmt_tc(n):
    return '%s%0*d' % (TC_PREFIX, TC_WIDTH, n)


def _doc_paths(docs_dir):
    """按逗号分隔的多个模式收集用例文件，同一文件只收一次。"""
    found = set()
    for pattern in (g.strip() for g in DOC_GLOB.split(',')):
        if pattern:
            found.update(p for p in docs_dir.rglob(pattern) if p.is_file())
    return sorted(found)


def _csv_numbers(text):
    """CSV 用例：取「用例编号」列（没有该列时取第 1 列）里整格就是编号的单元格。

    只看编号列：预期结果等列里也常提到别的编号（如「同 TC-0003」），不能算成本文件的用例。
    """
    rows = list(csv.reader(io.StringIO(text)))
    if not rows:
        return set()
    header = [c.strip() for c in rows[0]]
    if '用例编号' in header:
        col, body = header.index('用例编号'), rows[1:]
    else:
        col, body = 0, rows
    numbers = set()
    for row in body:
        m = RE_CSV_TC.match(row[col]) if col < len(row) else None
        if m:
            numbers.add(int(m.group(1)))
    return numbers


def load_docs(docs_dir):
    """返回 {用例文件名: set(编号)}，只收含编号的文件（md 看标题，csv 看编号列）。"""
    result = {}
    for path in _doc_paths(docs_dir):
        try:
            # utf-8-sig：testcase-design 的 CSV 带 BOM，不去掉会粘在第一个表头上
            text = path.read_text(encoding='utf-8-sig')
        except (UnicodeDecodeError, OSError) as exc:
            print('[WARN] 跳过无法读取的文件 %s: %s' % (path, exc))
            continue
        if path.suffix.lower() == '.csv':
            numbers = _csv_numbers(text)
        else:
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


def load_matrix(path, re_ref):
    """解析覆盖矩阵（Markdown 表格），按列名定位，容忍列序变动与额外列。

    必需列：含「预期方法数」的列、含「状态」的列；编号引用从整行文本里提。
    支持一份文件里**多个分节表格**（每节自带表头）；遇到不含必需列的
    其他表头（如环境基线表、四态表）会重置列映射，不会误当成数据行。
    返回 [{'tcs': set((md名,编号)), 'expected': int|None, 'status': str, 'line': int}]
    """
    lines = path.read_text(encoding='utf-8').splitlines()

    rows = []
    col_expected = col_status = None
    seen_header = False
    for i, line in enumerate(lines):
        if not line.lstrip().startswith('|') or _is_separator(line):
            continue
        cells = _cells_of(line)
        # 下一行是分隔行 → 本行是表头
        is_header = i + 1 < len(lines) and _is_separator(lines[i + 1])
        if is_header:
            exp = next((j for j, c in enumerate(cells) if '预期方法数' in c), None)
            sta = next((j for j, c in enumerate(cells) if '状态' in c), None)
            if exp is not None and sta is not None:
                col_expected, col_status, seen_header = exp, sta, True
            else:
                col_expected = col_status = None   # 其他表格，重置列映射
            continue
        if col_expected is None:
            continue
        tcs = set()
        for _md, first, tail in re_ref.findall(line):
            for n in expand_ref(first, tail):
                tcs.add((_md, n))
        if not tcs:
            continue           # 不含编号的行（小标题行、合计行）跳过
        raw = cells[col_expected] if col_expected < len(cells) else ''
        digits = re.sub(r'\D', '', raw)
        rows.append({
            'tcs': tcs,
            'expected': int(digits) if digits else None,
            'status': cells[col_status] if col_status < len(cells) else '',
            'line': i + 1,
        })
    if not seen_header:
        raise ValueError(
            '矩阵里找不到表头：需同时含「预期方法数」与「状态」两列（%s）' % path)
    return rows


def scan_methods(tests_dir, docs, re_ref, anno_re):
    """统计测试方法数，并把每个方法归属到编号。

    归属规则（写死，避免各人理解不同）：
      1. 先找距测试注解最近的用例名标记行（可以就在同一行，如 jest 的 it('…')）；
         **一个标记行只归一个方法**，按距离由近及远分配；**若两者之间隔着类/分组声明行，
         则该标记属类而不属方法**，不能被第一个方法领走（否则同类其余方法全部无法归属）
      2. 自己没有时，继承上方最近的**未被其他方法领走**的标记行（即类级标记）
      3. 一个标记覆盖 N 个编号时，该方法对每个编号各计 1/N，
         于是「各编号归属数之和 == 已归属方法数（= 总数 - 无法归属数）」恒成立，总账可对
      4. 两步都取不到 → 计入「无法归属」并单列，不静默算 0
    """
    total = 0
    per_tc = {}
    unattributed = []
    shared_from = set()

    for path in sorted(tests_dir.rglob('*')):
        if not path.is_file() or path.suffix.lower() in ('.class', '.jar', '.png', '.xlsx'):
            continue
        try:
            lines = path.read_text(encoding='utf-8').splitlines()
        except (UnicodeDecodeError, OSError):
            continue

        anno_lines = [i for i, l in enumerate(lines) if anno_re.search(l)]
        if not anno_lines:
            continue

        # 先把 marker 行分给方法：候选按距离由近及远，且不得跨过类声明。
        # 必须独占：否则没写标记的方法会领走邻居的标记，同行写法（距离 0）
        # 下每个方法还会错拿上一个方法的标记。
        candidates = []
        for i in anno_lines:
            for j in range(max(0, i - 3), min(len(lines), i + 4)):
                if not is_displayname_line(lines[j]):
                    continue
                # 标记行与方法之间隔着类声明 → 这是类级标记，不归该方法
                between = lines[min(i, j) + 1:max(i, j)]
                if any(RE_CLASS_DECL.match(bl) for bl in between):
                    continue
                refs = set()
                for md_name, first, tail in re_ref.findall(lines[j]):
                    for n in expand_ref(first, tail):
                        refs.add((md_name, n))
                if refs:
                    candidates.append((abs(j - i), i, j, refs))
        own = {}
        claimed = set()
        for _dist, i, j, refs in sorted(candidates, key=lambda c: c[:3]):
            if i not in own and j not in claimed:
                own[i] = (j, refs)
                claimed.add(j)

        # 未被领走的 marker 行 = 类级标记
        class_markers = []
        consumed = {v[0] for v in own.values()}
        for j, l in enumerate(lines):
            if j in consumed or not is_displayname_line(l):
                continue
            refs = set()
            for md_name, first, tail in re_ref.findall(l):
                for n in expand_ref(first, tail):
                    refs.add((md_name, n))
            if refs:
                class_markers.append((j, refs))

        for i in anno_lines:
            total += 1
            if i in own:
                refs = own[i][1]
                share = 1.0 / len(refs)
                if len(refs) > 1:
                    shared_from.add(path)
                for key in refs:
                    per_tc[key] = per_tc.get(key, 0) + share
                continue
            inherited = None
            for j, refs in class_markers:
                if j < i:
                    inherited = refs
            if inherited:
                share = 1.0 / len(inherited)
                shared_from.add(path)
                for key in inherited:
                    per_tc[key] = per_tc.get(key, 0) + share
            else:
                unattributed.append((path, i + 1))

    return total, per_tc, unattributed, shared_from


def main():
    parser = argparse.ArgumentParser(description='用例编号引用反向校验')
    parser.add_argument('--docs', help='用例文档所在目录（除 --selftest 外必需）')
    parser.add_argument('--tests', help='测试源码所在目录（除 --selftest 外必需）')
    parser.add_argument('--quiet', action='store_true', help='只输出问题与汇总，不列明细')
    parser.add_argument('--out', help='把报告写入指定 UTF-8 文件（规避控制台编码问题）')
    parser.add_argument('--tc-prefix', default='TC-', help='编号前缀，默认 TC-')
    parser.add_argument('--tc-width', type=int, default=4, help='编号补零位数，默认 4')
    parser.add_argument('--test-marker', default='@DisplayName',
                        help='用例名声明行的标记，默认 @DisplayName（JUnit5）；'
                             'pytest 用 "def test_"，jest 用 "it("，go 用 "func Test"')
    parser.add_argument('--doc-glob', default='*.md,*.csv',
                        help='用例文档文件名模式，逗号分隔多个，默认 *.md,*.csv')
    parser.add_argument('--negation-pattern', default=None,
                        help='「声明不覆盖」的正则，默认中文词表；非中文项目必须显式传')
    parser.add_argument('--matrix', default=None,
                        help='覆盖矩阵文件（Markdown 表格，需含「预期方法数」与「状态」两列）；'
                             '传入后额外做矩阵↔代码对账')
    parser.add_argument('--test-annotation-pattern',
                        default=r'^\s*@(Test|ParameterizedTest|RepeatedTest|TestFactory)\b',
                        help='测试方法注解行的正则；pytest 用 "^\\s*def test_"，'
                             'jest 用 "^\\s*(it|test)\\("，go 用 "^func Test"')
    parser.add_argument('--selftest', action='store_true',
                        help='只跑内置的编号展开回归用例，不扫目录')
    args = parser.parse_args()

    configure(args.tc_prefix, args.tc_width, args.test_marker, args.doc_glob,
              args.negation_pattern)

    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')

    if args.selftest:
        bad = _selftest()
        if bad:
            print('SELFTEST FAIL')
            for name, got, want in bad:
                print('  %s -> %s，应为 %s' % (name, got, want))
            return 1
        print('SELFTEST PASS —— 编号展开、分隔行、CSV 编号列、方法归属的回归用例全部通过')
        return 0

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

    if not args.docs or not args.tests:
        print('[ERROR] 需要同时传 --docs 与 --tests（或改用 --selftest）')
        return 2
    docs_dir, tests_dir = Path(args.docs), Path(args.tests)
    if not docs_dir.is_dir():
        print('[ERROR] 用例目录不存在: %s' % docs_dir)
        return 2
    if not tests_dir.is_dir():
        print('[ERROR] 测试目录不存在: %s' % tests_dir)
        return 2

    docs = load_docs(docs_dir)
    if not docs:
        print('[ERROR] %s 下按 %s 没找到任何含 %s编号的用例文档'
              '（md 看标题开头，csv 看「用例编号」列）'
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

    rows = None
    waived = []
    if args.matrix:
        matrix_path = Path(args.matrix)
        if not matrix_path.is_file():
            print('[ERROR] 覆盖矩阵文件不存在: %s' % matrix_path)
            return 2
        try:
            rows = load_matrix(matrix_path, build_ref_regex(docs.keys()))
        except ValueError as exc:
            print('[ERROR] %s' % exc)
            return 2
        # 状态写「不覆盖（原因）」= 有意不做，不再算进未覆盖
        waived_keys = {k for row in rows if re.match(r'[`*\s]*不覆盖', row['status'])
                       for k in row['tcs']}
        waived = [k for k in uncovered if k in waived_keys]
        uncovered = [k for k in uncovered if k not in waived_keys]

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
    if rows is not None:
        print('覆盖矩阵里标「不覆盖」的编号: %d 条' % len(waived))
        if waived and not args.quiet:
            for md_name, n in waived:
                print('  ⚪ %s#%s' % (md_name, fmt_tc(n)))
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

    print('【4】未覆盖编号（既无测试、也没在代码或矩阵里声明不覆盖）: %d' % len(uncovered))
    if uncovered and not args.quiet:
        current = None
        for md_name, n in uncovered:
            if md_name != current:
                print('  %s' % md_name)
                current = md_name
            print('    %s' % fmt_tc(n), end='')
        print()
    print()

    # ---- 矩阵 ↔ 代码 对账（仅当传了 --matrix）----
    if rows is not None:
        re_ref = build_ref_regex(docs.keys())
        anno_re = re.compile(args.test_annotation_pattern)
        total_methods, per_tc, unattributed, shared_from = scan_methods(
            tests_dir, docs, re_ref, anno_re)

        matrix_tcs = set()
        written_tcs = set()
        expected_sum = 0
        for row in rows:
            matrix_tcs |= row['tcs']
            if '已写' in row['status']:
                written_tcs |= row['tcs']
            if row['expected'] is not None:
                expected_sum += row['expected']

        attributed = total_methods - len(unattributed)
        print('【5】矩阵对账（%s）' % matrix_path.name)
        print('  矩阵行数 %d，涵盖编号 %d 个，标「已写」的编号 %d 个'
              % (len(rows), len(matrix_tcs), len(written_tcs)))
        print('  测试方法 %d 个：已归属 %d、无法归属 %d（impl 类测试无编号属正常）'
              % (total_methods, attributed, len(unattributed)))
        print('  矩阵预期方法数合计 %d（❗一行盖多条编号时会重复计，'
              '不可与实际方法数直接相比）' % expected_sum)
        print('  归属数之和 %.2f（应等于已归属数 %d）%s'
              % (sum(per_tc.values()), attributed,
                 '✅' if abs(sum(per_tc.values()) - attributed) < 0.01 else '🔴 不自洽'))
        if abs(sum(per_tc.values()) - attributed) >= 0.01:
            fail = True

        # A 虚报已写：矩阵说已写，但没有任何测试引用它
        overclaimed = sorted(k for k in written_tcs if k not in qualified)
        if overclaimed:
            fail = True
            print('  🔴 A 虚报已写（矩阵标已写但无测试引用）: %d' % len(overclaimed))
            for md_name, n in overclaimed:
                print('     %s#%s' % (md_name, fmt_tc(n)))
        else:
            print('  ✅ A 无虚报已写')

        # B 矩阵漏登：测试引用了，矩阵里没这一行
        unlisted = sorted(k for k in qualified if k not in matrix_tcs)
        if unlisted:
            fail = True
            print('  🔴 B 矩阵漏登（已有测试但矩阵里没登记）: %d' % len(unlisted))
            for md_name, n in unlisted:
                print('     %s#%s' % (md_name, fmt_tc(n)))
        else:
            print('  ✅ B 矩阵无漏登')

        # C 已写但零归属：比 A 更严——引用可能只出现在类注释里，
        #   但没有任何一个测试方法真正归属到这条编号
        zero = sorted(k for k in written_tcs if per_tc.get(k, 0) <= 0)
        if zero:
            fail = True
            print('  🔴 C 标已写但零方法归属（引用只在注释里，没落到具体测试方法）: %d'
                  % len(zero))
            for md_name, n in zero:
                print('     %s#%s' % (md_name, fmt_tc(n)))
        else:
            print('  ✅ C 每条已写编号都有方法归属')

        # D 逐条比对（咨询级）：一行盖 N 个编号时归属会按 1/N 分摊，
        #   所以这里是小数，只能作参考，不卡门禁
        mismatch = []
        for row in rows:
            if row['expected'] is None or '已写' not in row['status']:
                continue
            for key in sorted(row['tcs']):
                actual = per_tc.get(key, 0)
                if abs(actual - row['expected']) > 0.01:
                    mismatch.append((key, row['expected'], actual, row['line']))
        print('  %s D 逐条方法数与预期不一致（咨询级，不卡门禁）: %d'
              % ('🟡' if mismatch else '✅', len(mismatch)))
        if mismatch and not args.quiet:
            for (md_name, n), exp, act, lineno in mismatch:
                print('     第%d行  %s#%s  预期 %d / 归属 %.2f'
                      % (lineno, md_name, fmt_tc(n), exp, act))
            print('     ↳ 归属是小数：一个标记盖了多条编号、按 1/N 分摊，改成方法级标注可让本项变准；'
                  '归属是整数：实际方法数就是和矩阵预期不同，改矩阵或补测试')

        if unattributed and not args.quiet:
            print('  ℹ️  无法归属的测试方法（impl 类无编号属正常，判据类则是漏标注）:')
            for path, lineno in unattributed:
                print('     %s:%d' % (path, lineno))
        print()

    print('=' * 68)
    if fail:
        print('结果: FAIL —— 门禁不通过（见上方 🔴 项）')
        return 1
    print('结果: PASS —— 无悬空引用（无锚点 %d 处、可推断裸号 %d 处、疑似虚报 %d 处需人工确认）'
          % (len(bare_noanchor), len(bare_single), len(suspected)))
    return 0


if __name__ == '__main__':
    sys.exit(main())
