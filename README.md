# testcase-to-unittest

[![skills.sh](https://skills.sh/b/zouaiyong/testcase-to-unittest)](https://skills.sh/zouaiyong/testcase-to-unittest)

把已定稿、带 TC 编号的功能测试用例落成自动化单测。断言只来自用例判据；实现不符时测试保持失败，交给开发改实现。不改断言，不改开发代码。

用例还没写用 `testcase-design`。前提是用例已定稿、实现代码已存在。执行规则、六阶段流程、四条硬约束都在 [SKILL.md](SKILL.md)，每阶段的完成标准在 [references/stage-contracts.md](references/stage-contracts.md)。

![skill 全景图](assets/overview.png)

## 安装

```bash
npx skills add zouaiyong/testcase-to-unittest
```

会装到 `~/.agents/skills/testcase-to-unittest`。WorkBuddy、Claude Code 不读这个目录，装完后让对应 Agent 把该路径软链接到自己的 skills 目录（WorkBuddy：`~/.workbuddy/skills/testcase-to-unittest`；Claude Code：`~/.claude/skills/testcase-to-unittest`）。Windows 建不了软链接就用目录联接。链好后新开一轮对话即可被发现。

也可以把本仓库直接放到上述目录。目录里必须有 `SKILL.md`。

## 怎么用

对已经加载本 skill 的 Agent 说「写单测」「补单测」或「对着用例把能单测的写成单测」，并给两样东西：

1. 定稿功能用例的路径：`{需求名称}-测试用例.md` 或 `{需求名称}-测试用例.csv`（`testcase-design` 的两种产物都能读）。
2. 被测代码所在的项目。

没给路径时 Agent 会先问，不会自己到仓库外翻。同一需求 md 和 csv 都有时，先确认以哪份为准。已经有一部分单测、只补一批时，直接说补哪几条或哪个模块。用例在执行过程中改了，告诉 Agent「用例更新了」，它会重新入库换基线。

Agent 只写纯口径层和规则层的测试。页面表现和必须连真库、真接口才能成立的判据登记成缺口，不写自动化脚本。

## 交付物

都落在**被测项目**的 `doc/testcases/` 和测试源码树里，不在本 skill 仓库：自动化覆盖矩阵、评审记录、七节单测报告（第 6 节即失败定位），以及分层测试代码。各份的模板与「通过」的判定条件见 [references/stage-contracts.md](references/stage-contracts.md) 阶段 5。

交付前 Agent 会跑带 `--matrix` 的追溯校验（拦截悬空引用、虚报已写、未覆盖编号与残留 `待写`）。注意追溯脚本退出码 0 只是门禁之一，单测报告写「通过」还要求测试全量的结果摘要存在，且从该行抄出的失败、错误、跳过都是 0、独立评审通过且无待业务拍板项：

```bash
python <skill目录>/scripts/check_tc_refs.py --docs doc/testcases --tests <测试源码目录> --matrix <覆盖矩阵>
```

## 开发

- `python scripts/check_tc_refs.py --selftest`：追溯脚本回归。
- `evals/`：skill 自身的评测——最小 Maven fixture、提示词与断言，见 [evals/README.md](evals/README.md)。
