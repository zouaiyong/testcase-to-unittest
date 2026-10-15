# evals：skill 自身的评测

按 skill-creator 的流程，用同一组提示词分别跑「带 skill」和「不带 skill」，再按 `evals.json` 里的 expectations 打分。fixture 是一个能离线构建的最小 Maven 项目，答案卡在 `fixtures/ANSWER-KEY.md`，只给打分方看。

## 目录

```
evals/
├── evals.json                 # 3 条提示词 + 可核对的 expectations
├── README.md
└── fixtures/
    ├── ANSWER-KEY.md          # 四态、埋下的两处实现不符、预期交付
    ├── cases/
    │   └── 存储费管理-测试用例.md   # 10 条 TC，testcase-design XMind 版格式
    └── storage-fee-demo/      # Java 8 / JUnit 5.7 / Mockito 3.6 / surefire 2.22.2
        ├── pom.xml
        └── src/
            ├── main/java/demo/fee/   # StorageFeeCalculator（纯口径）、StorageFeeBillService（规则）
            └── test/java/demo/fee/   # SmokeTest：基线 Tests run: 1
```

## 跑一轮

1. 把 `fixtures/` 整个复制到工作区（如 `../testcase-to-unittest-workspace/iteration-1/eval-1/with_skill/fixture/`），不要在仓库内原地跑：skill 会往项目里写 `doc/testcases/` 和测试代码。
2. 把 `evals.json` 里提示词中的 `{fixture}` 替换成复制后的绝对路径。
3. 带 skill 的运行：子 agent 的 prompt 给 skill 路径 + 提示词；不带 skill 的运行：同一提示词，不给 skill。
4. 跑完后对照 `ANSWER-KEY.md` 和每条 eval 的 expectations 打分，写进 `grading.json`（字段 `text` / `passed` / `evidence`）。
5. 每轮迭代后如果改了 skill，重跑并与上一轮比较。

## 三条 eval 各测什么

| id | 名字 | 考的是 |
|---|---|---|
| 1 | full-run-keeps-deviations-red | 完整六阶段；两处实现不符是否被保持为失败；报告、矩阵、追溯是否齐全 |
| 2 | asks-for-case-path-before-touching-code | 没给用例路径时是否先问，而不是先读实现 |
| 3 | refuses-to-green-wash | 用户施压要「改绿 + 写通过」时，硬约束 1 是否守得住 |

## fixture 为什么这样设计

- TC-0001 第一组数据在 HALF_UP 和 DOWN 下结果相同，第二组才分得开。只写一组数据、或把因子选成平凡值的测试抓不到这条偏差，这正是 assertion-rules 第 8 条要防的。
- TC-0005 的文案偏差只差两个字（停用 / 关闭），包含匹配会漏，逐字比对才抓得到（第 2 条）。
- TC-0004 与 TC-0005 共用同一个方法、校验有先后，用来考「证明拦下它的是这条规则」（第 6 条）。
- TC-0006 最后一行是页面表现，考按行归层而不是整条定性。
- TC-0008 / 0009 / 0010 分别对应仅人工、无实现、判据未定，让四态都有一条。
