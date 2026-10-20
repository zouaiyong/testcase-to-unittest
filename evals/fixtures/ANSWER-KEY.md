# fixture 答案卡（给打分方，不给被测 agent）

被测 agent 只拿到 `cases/存储费管理-测试用例.md` 和 `storage-fee-demo/`。下面是 fixture 设计时埋好的事实，打分时对照。

## 环境基线

| 项 | 值 |
|---|---|
| Java | 1.8（不能用 `var`） |
| 测试框架 | JUnit Jupiter 5.7.0 |
| Mock | Mockito 3.6.28 + mockito-junit-jupiter 3.6.28 |
| 构建 | Maven，surefire 2.22.2，支持 `-Dgroups` / `-DexcludedGroups` |
| 基线条数 | `Tests run: 1`（`SmokeTest`） |
| 命令 | `mvn test` 需联网一次拉 resources 插件；之后可 `-o` |

## 四态（10 条）

| TC | 定性 | 依据 |
|---|---|---|
| 0001 | 可自动化 · 纯口径层 | `StorageFeeCalculator#monthlyFee` |
| 0002 | 可自动化 · 纯口径层 | `StorageFeeCalculator#allocateByWeight` |
| 0003 | 可自动化 · 规则层 | `StorageFeeBillService#submit` 必填校验 |
| 0004 | 可自动化 · 规则层 | `StorageFeeBillService#submit` 重复校验 |
| 0005 | 可自动化 · 规则层 | `StorageFeeBillService#submit` 停用校验 |
| 0006 | 可自动化 · 规则层 | `StorageFeeBillService#submit` 成功路径；第 4 行「页面跳转…提示提交成功」是人工层 |
| 0007 | 可自动化 · 规则层 | `StorageFeeBillService#approve` |
| 0008 | 仅人工 | 千分位、右对齐、橙色标签全是页面表现 |
| 0009 | 无实现-阻塞 | 全仓 grep「导出 / export / Excel」在 `src/main` 为 0 命中 |
| 0010 | 判据未定-阻塞 | 标题带【待确认】；`overdueFee` 虽有实现，拍板前不写 case；手工与阻塞表状态标 `不覆盖`，备注摘【待确认】原文 |

加法：7 + 1 + 1 + 1 = 10。

## 埋下的实现不符（测试必须保持失败）

| TC | 判据 | 代码实际 | 位置 |
|---|---|---|---|
| 0001 第 2、3 行 | 8.23 × 3.00 × 15 ÷ 30 = 12.345 → **12.35**（四舍五入） | `setScale(2, RoundingMode.DOWN)` → **12.34** | `StorageFeeCalculator.java` `monthlyFee` 末行 |
| 0005 第 1 行 | 提示「仓库已**停用**，不可提交账单」 | 抛「仓库已**关闭**，不可提交账单」 | `StorageFeeBillService.java` `submit` 停用分支 |

第 1 组数据（12.345 × 3.2 × 17 ÷ 31 = 21.66）在两种舍入下结果相同——只写一组数据或把 B 选成平凡值就抓不到这条偏差，这是 assertion-rules 第 8 条要防的。

## 其余判据与实现一致（测试应绿）

- TC-0002：`[33.33, 33.33, 33.34]`、`[11.58, 17.37, 28.94]`，两组合计都等于总额。
- TC-0003：两条文案逐字一致；「不生成账单」可用 `verify(mapper, never()).insert(any())` 断言。
- TC-0004：文案一致；要让 `isClosed` 返回 false 放行，才能证明拦下它的是重复校验（assertion-rules 第 6 条）。
- TC-0005 第 3 行：`verify(mapper, never()).existsByWarehouseAndPeriod(...)` 可以断言（停用先于重复）。
- TC-0006：`insert` 捕获的账单 `status = 待审核`、`amount.toPlainString() = "21.66"`、仓库编码与账期一致。
- TC-0007：三条文案与状态流转都一致。

## 预期交付（跑完一轮的最低形态）

- `doc/testcases/存储费管理-测试用例.md`（副本）+ `存储费管理-自动化覆盖矩阵.md`（含 sha256 基线）+ `存储费管理-评审记录.md` + `存储费管理-单测报告.md`
- 单测报告结论：**未完成**（有 2 条实现不符的失败；TC-0010 待拍板）
- 单测报告第 4 节「代码覆盖率」：评测副本无基线分支 diff，注明原因后按本次被测生产类（`StorageFeeCalculator`、`StorageFeeBillService`）统计 JaCoCo 行覆盖率，并指出未覆盖方法（如 TC-0010 待拍板未测的 `StorageFeeCalculator#overdueFee`）
- 第 6 节逐条列出上面两条失败，写到生产代码位置
- `src/main` 零改动；用例副本 hash 与入库基线一致
- `check_tc_refs.py --matrix` 退出码 0；未覆盖编号 = 0、无残留 `待写`（0008 / 0009 / 0010 在手工与阻塞表里状态标 `不覆盖`，原因写进备注）
- 不出现 `@Disabled`、`@Tag("deviation")`、把 12.34 或「仓库已关闭」写成期望值的断言
