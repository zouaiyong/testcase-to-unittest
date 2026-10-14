# testcase-to-unittest

[![skills.sh](https://skills.sh/b/zouaiyong/testcase-to-unittest)](https://skills.sh/zouaiyong/testcase-to-unittest)

把已定稿、带 TC 编号的功能测试用例落成自动化单测。断言只来自用例判据；实现不符时测试保持失败，交给开发改实现。不改断言，不改开发代码。

用例还没写用 `testcase-design`，评审用例本身用 `testcase-closed-loop`。前提是用例已定稿、实现代码已存在。执行规则在 [SKILL.md](SKILL.md)。

![skill 全景图](skill全景图.png)

定性后三条出路：人工层和集成层只登记缺口；整条无实现或判据未定的不进矩阵；纯口径层和规则层先写覆盖矩阵，再写单测，独立评审后交付。

## 安装

`SKILL.md` 在仓库根目录。装完后新开一个会话。追溯脚本需要 Python 3。

当前项目：

```bash
npx skills add zouaiyong/testcase-to-unittest
```

本机所有项目加 `-g`。Windows 符号链接失败时加 `--copy`：

```bash
npx skills add zouaiyong/testcase-to-unittest -g --copy
```

指定 agent：`-a cursor`、`-a claude-code`、`-a codex`。更新：`npx skills update testcase-to-unittest`。

OpenClaw 从 Git 安装：

```bash
openclaw skills install git:zouaiyong/testcase-to-unittest
```

ClawHub 上架后：`openclaw skills install @<owner>/testcase-to-unittest`。手动克隆时文件夹名保持 `testcase-to-unittest`，放到对应 agent 的 skills 目录（Cursor 用户级是 `~/.cursor/skills/`，Claude Code 是 `~/.claude/skills/`，Codex 是 `~/.agents/skills/`）。

目录页在有人用 CLI 安装后出现：[skills.sh/zouaiyong/testcase-to-unittest](https://skills.sh/zouaiyong/testcase-to-unittest)。

## 怎么用

告诉 agent 两件事：定稿用例路径（`{需求名称}-测试用例.md` 或 `.csv`），以及被测项目。没有路径时先问。

产物写在被测项目的 `doc/testcases/`：覆盖矩阵、评审记录、单测报告。引用用例写成 `文件名#TC-0008`。追溯校验：

```bash
python <skill目录>/scripts/check_tc_refs.py --docs doc/testcases --tests <测试源码目录> --matrix <覆盖矩阵>
```
