# 技术栈附录：Java / Maven / JUnit5 / Mockito / MyBatis Plus

阶段 0 用这份清单。**每一条都是实测踩过并确认了根因的**，不是通用建议。

这是按栈拆分的附录之一。其他技术栈（pytest / jest / go test 等）按同样格式
新建 `<栈名>-pitfalls.md`：先给探测清单，再给分级坑列表（🔴 会造成假绿或编译失败、
🟠 会造成断言无效、🟡 体验与可维护性）。

## 探测清单

先查版本，再决定怎么写测试。**查本地仓库比查 pom 更准**（pom 里常是 parent 托管、看不到实际版本）。

macOS / Linux：

```bash
ls ~/.m2/repository/org/springframework/boot/spring-boot-starter-test/
ls ~/.m2/repository/org/junit/jupiter/junit-jupiter/
ls ~/.m2/repository/org/mockito/mockito-core/
ls ~/.m2/repository/com/baomidou/mybatis-plus-core/
ls ~/.m2/repository/org/apache/maven/plugins/maven-surefire-plugin/
ls ~/.m2/repository/org/junit/vintage/          # 不存在 = 没有 vintage 引擎
java -version                                     # 决定能不能用 var / records / switch 表达式
```

Windows PowerShell（注意用 `;` 而不是 `&&` 分隔语句）：

```powershell
$m2 = "$HOME\.m2\repository"
'spring-boot-starter-test','junit\jupiter\junit-jupiter','mockito\mockito-core',
'baomidou\mybatis-plus-core','apache\maven\plugins\maven-surefire-plugin' |
  ForEach-Object { Get-ChildItem "$m2\org\$_" -Directory -ErrorAction SilentlyContinue |
                   Select-Object @{n='Artifact';e={$_Parent.Name}}, Name }
Test-Path "$m2\org\junit\vintage"    # False = 没有 vintage 引擎
java -version
```

> 直接看目录名就是版本号，比跑 `mvn dependency:tree` 快很多，也不需要能联网。

必须记录的 6 项：

| 项 | 为什么必须知道 |
|---|---|
| Java 语言级别 | Java 8 **没有 `var`**，写了编译不过 |
| Spring Boot 版本 → 测试引擎完整性 | 决定 starter-test 里带了什么（2.4 起不含 vintage 引擎）；这就是 SKILL.md 六项里的「测试引擎是否齐全」 |
| JUnit 版本（4 还是 5） | 两套 API 的注解、断言参数顺序、扩展模型全不同 |
| Mockito 版本 | **5.x 之前 `mockStatic` 必须额外加 `mockito-inline`** |
| ORM 及版本 | 链式 API 的 mock 姿势、方法返回类型都随版本变 |
| surefire 版本 | 2.22.0+ 才原生支持 JUnit Platform 与 `@Tag` 过滤 |

## 🔴 坑 1：JUnit4 写法会静默不执行

**链条**：Spring Boot 2.4 起 `spring-boot-starter-test` 不再包含 `junit-vintage-engine`
→ surefire 检测到 junit-platform 就选 `JUnitPlatformProvider`
→ Platform 只认已注册的 Engine（有 jupiter、没有 vintage）
→ 而 pom 里若还显式声明着 `junit:junit`，`import org.junit.Test` **能编译通过**
→ 结果：测试类编译成功、文件名被 `**/*Test.java` 匹配到、**没有任何引擎认领它**
→ 一条不跑，Maven 输出 `Tests run: 0` + **BUILD SUCCESS**。

这是整个技术栈里最危险的一条：**测试套件看着在长、覆盖率报告一片绿、实际一条断言都没执行过**。
而 pom 里那个 JUnit4 依赖正在主动诱导人踩进去。

**处置**：统一 JUnit 5，一行 JUnit 4 都不写。最好把 pom 里的 `junit:junit` 删掉，
让 JUnit4 写法**编译失败**（响亮）而不是静默不跑（无声）。
若不能改 pom，就约定 + 事后校验：扫测试源码里是否出现 `org.junit.Test`（非 jupiter）。

**不要**通过加 `junit-vintage-engine` 来「兼容」—— 那等于把两套范式并存固化下来。

两套 API 的关键差异（混写会静默出错）：

| | JUnit4 | JUnit5 |
|---|---|---|
| 测试注解 | `org.junit.Test` | `org.junit.jupiter.api.Test` |
| 初始化 | `@Before` / `@BeforeClass` | `@BeforeEach` / `@BeforeAll` |
| 扩展 | `@RunWith(Xxx.class)`（**只能一个**） | `@ExtendWith(Xxx.class)`（可叠加） |
| 断言消息位置 | `assertEquals(msg, expected, actual)` | `assertEquals(expected, actual, msg)` |
| 参数化 | `@RunWith(Parameterized.class)` + 静态方法，一个数据集一个类 | `@ParameterizedTest` + `@CsvSource`/`@CsvFileSource`/`@MethodSource` |
| 异常断言 | `@Test(expected=X.class)`（**断不了消息**） | `assertThrows` **返回异常对象**，可继续断消息 |
| 分组 | `@Category`（笨重） | `@Tag` |
| 用例名 | 无 | `@DisplayName` |
| 嵌套 | 不支持 | `@Nested` |

混用的隐性失败：在 JUnit5 类里误写 `@Before`，**初始化根本不执行** → 后续 NPE，
而且不会提示你注解写错了。

## 🔴 坑 2：`-Dtest=类名` 匹配不到 `@Nested` 内部类

surefire 2.22.2 实测：测试方法全部放在 `@Nested` 内部类里时，
`-Dtest=SomeTest` 报 `Tests run: 0` 且 **BUILD SUCCESS**。

**处置**：跑全量，或用 `-Dtest=SomeTest*`。**永远靠 `Tests run: N` 判断，不靠 BUILD SUCCESS。**

输出里根本没有 `Tests run` 这一行时见坑 3。

## 🔴 坑 3：`maven.test.skip` / `skipTests` 让退出码变成假绿

Maven 3.9.16、compiler 3.8.1、surefire 2.22.2 实测。根 pom 的 `<properties>` 写 `<maven.test.skip>true</maven.test.skip>` 时，子模块直接 `mvn test`：

- compiler 打 `Not compiling test sources`，测试源码不编译
- surefire 打 `Tests are skipped.`
- 输出里没有 `Tests run`
- 退出码 0，`BUILD SUCCESS`
- 同一条必然会失败的测试，加上 `-Dmaven.test.skip=false` 后是 `Tests run: 1, Failures: 1`，退出码 1

`skipTests`（pom `<properties>` 里 `<skipTests>true</skipTests>`，或命令行 `-DskipTests`）只打 `Tests are skipped.`，测试源码仍会编译，同样没有 `Tests run`，退出码仍是 0。

跳过还有第三种写法：surefire 插件的 `<configuration><skip>true</skip></configuration>`（含 `pluginManagement` 里的）。现象同 `skipTests`，但**命令行 `-Dmaven.test.skip=false -DskipTests=false` 关不掉它**，实测仍是 `Tests are skipped.`、退出码 0。插件 `<configuration>` 里写死的值优先于属性，只有改 pom 才能关。

三种写法与命令行能否关掉：

| 跳过写在哪 | 直接 `mvn test` | 命令行 `-Dmaven.test.skip=false -DskipTests=false` |
|---|---|---|
| `<properties>` 里 `maven.test.skip=true` | `Not compiling test sources` + `Tests are skipped.`，退出码 0 | 测试执行，有 `Tests run` |
| `<properties>` 里 `skipTests=true` | `Tests are skipped.`，退出码 0 | 测试执行，有 `Tests run` |
| surefire `<configuration><skip>true</skip>` | `Tests are skipped.`，退出码 0 | **仍跳过**，退出码 0 |

**处置**：没有结果摘要就是没跑，按硬约束 4 处理，不能写成 0 失败 0 错误 0 跳过。阶段 0 查根 pom、父 pom 的 `<properties>`，以及 surefire 的 `<configuration>`（含 `pluginManagement`）。属性写法加 `-Dmaven.test.skip=false -DskipTests=false` 就能跑起来；`<configuration><skip>` 写法命令行关不掉，停下来报告用户，由用户决定怎么处理。pom 属于生产代码，不得为了把测试跑起来改它。通过与否仍然只认重跑之后的摘要行。

## 🔴 坑 4：`RETURNS_SELF` 会把泛型终结方法也当成链式中间方法

mock ORM 的链式查询时，`RETURNS_DEEP_STUBS` 会因泛型擦除在链式调用中抛 NPE，
所以要改用 `RETURNS_SELF`。但 `RETURNS_SELF` 的判定是
**「擦除后的返回类型能否容纳 mock 自身」**：

| 终结方法 | 擦除后返回类型 | 结果 |
|---|---|---|
| `one()` | `Object`（泛型 `T` 擦除） | ⚠️ **能容纳 → 返回 wrapper 自己 → 调用方赋值时 ClassCastException** |
| `list()` | `List` | 安全，回落默认值（空集合） |
| `count()` | `Integer` | 安全，回落默认值（0） |
| `update()` | `boolean` | 安全，回落 `false` |

**处置**：在共享脚手架里把 `one()` **统一预打桩为 `null`**，别指望每个测试类自己记得。
预打桩那一行要写在**泛型上下文的辅助方法内**——此时 `one()` 的静态类型就是 `T`，
编译器不插入 `checkcast`，打桩动作本身不会 CCE。

显式覆盖了 `one()` 的测试类会掩盖这个 bug，所以它只在**依赖默认值的类**里爆发。

## 🟠 坑 5：链式 mock 吞掉查询条件 → 维度类判据原理上不可断言

`RETURNS_SELF` 让链上所有 `eq/in/ge/le/last/orderBy` 变成返回自身的空操作，
**WHERE 条件完全不可验证**。凡是判据写成「按 X+Y+Z 维度查询/查重/统计」的用例都中招。

三条出路，按优先级：

1. 被测服务把维度封装成了**具名方法**（如 `getByDimension(date, wh, feeType, sku)`）
   → 直接用 `ArgumentCaptor` 捕入参断言。**注意 `anyString()` 不匹配 `null`**：
   stub 不命中时 mock 默认返回 `null`，恰好等于「查无重复」的预期，测试反而更绿。
2. 改用**真实**的链式 wrapper 包一个 mock `BaseMapper`，终结操作落到 mapper 上，
   再捕获 wrapper 断言 `getSqlSegment()` / `getParamNameValuePairs()`。
3. 下沉到真库集成测试。

**验不了就在 `@DisplayName` 里明说验不了，禁止空头承诺。**

## 🟠 坑 6：链式 mock 只能用于 Service，不能用于 Mapper

`BaseMapper` 没有 `lambdaQuery()`，把链式 mock 辅助方法套上去会 ClassCastException。
Mapper 一律直接 `when(mapper.xxx(...)).thenReturn(...)` 打桩。

## 🟠 坑 7：ORM 的 lambda 缓存需要手动预热

不起容器时实体未被扫描注册，lambda 方法引用（`Entity::getField`）会抛
`can not find lambda cache`。在 `@BeforeEach` 里对**每个出现在 lambda 引用中的实体**
调用一次 `TableInfoHelper.initTableInfo(new MapperBuilderAssistant(new MybatisConfiguration(), ""), Entity.class)`。

## 🟠 坑 8：Bean Validation 注解在 Controller 层触发，直接调 Service 测不到

`@NotEmpty` / `@NotBlank` / `@Size` 由 Spring MVC 的 `@Validated` 在入参绑定时触发。
不起容器就直接调业务方法，这些校验**一条都不会执行**。

**处置**：在测试里手动执行等价校验，拿真实 message：

```java
Validator validator = Validation.buildDefaultValidatorFactory().getValidator();
Set<ConstraintViolation<T>> violations = validator.validate(po);
```

这比「反射断言注解存在」强得多——后者只证明注解在，不证明校验会拦、文案是什么。
校验器由 `spring-boot-starter-validation` 提供，通常已在 classpath。

两个细节：
- 违规集合的**遍历顺序不确定**，断言前先排序，或做无序比对
- 按 `propertyPath` 取单条时，返回 `null` 无法区分「无违规」与「路径名写错」；
  用于 `assertNull` 断言「应放行」时**必须在同一用例内配一条正向断言兜底**，否则路径打错就是永真断言

## 🟡 坑 9：`@Tag` 沿嵌套类层级叠加

`@Nested` 内部类会继承外层类的 Tag，方法级 Tag 是**追加**不是覆盖。
所以「外层 `@Tag("case")` + 方法 `@Tag("impl")`」的测试同时带两个 Tag，
只用 `-Dgroups=case` 会把它算进判据门禁。

**处置**：门禁命令为 `-Dgroups=case -DexcludedGroups=impl`，排除项只有 `impl`；实现和用例不符的测试按硬约束 1 保持失败，不靠分组从失败列表里消失。
并每次做加减核对：`全量 = 判据门禁（含失败）+ 带 impl 标记的测试（纯 impl + case/impl 叠加）`，对不上说明 Tag 打错了。
或者干脆**不在嵌套类上打 Tag，逐个方法打**（更啰嗦但无歧义）。

## 🟡 坑 10：静态上下文调用需要 inline mock maker

业务代码里若有 `XxxHolder.user()` 这类静态调用，需要 `mockStatic`。
**Mockito 5.x 之前必须额外引入 `mockito-inline`**，只有 `mockito-core` 会直接抛异常。

先 grep 出静态调用点，确认它们是否落在被测路径上——不在就完全不需要引入这个依赖。

## 🟡 坑 11：断言 `BigDecimal` 要同时锁值和小数位

`assertEquals(new BigDecimal("1.0"), new BigDecimal("1.0000"))` **会失败**（`equals` 比 scale），
但用 `compareTo` 又会漏掉「精度位数不对」这个真正的判据。

**处置**：统一用 `toPlainString()` 比对字符串。
既锁数值又锁 scale，还顺带避开科学计数法。

## 🟡 坑 12：`mvn clean` 在离线模式可能因插件依赖缺失而失败

`-o`（离线）下若本地仓库缺 clean 插件的传递依赖（如 `maven-shared-utils`），
会报 `A required class was missing`。这是环境问题，与测试代码无关。
去掉 `-o` 让它联网补齐即可；**别把这个失败误判成代码错误**。

## 断言 `lambdaUpdate().set(列, 值)` 改了哪个字段

链式 update 被 mock 后 `.set()` 只留下调用记录。只 `verify(...).update()` 是不够的——
把要设的值改错、或整行删掉某个 `set`，`update()` 照样会被调用。

要断言到具体字段，需要把 `SFunction` 方法引用解析成属性名：

```java
public static String propertyOf(SFunction<?, ?> fn) {
    try {
        Method writeReplace = fn.getClass().getDeclaredMethod("writeReplace");
        writeReplace.setAccessible(true);
        SerializedLambda lambda = (SerializedLambda) writeReplace.invoke(fn);
        String name = lambda.getImplMethodName();
        if (name.startsWith("get")) {
            name = name.substring(3);
        } else if (name.startsWith("is")) {
            name = name.substring(2);
        }
        return Introspector.decapitalize(name);
    } catch (ReflectiveOperationException e) {
        throw new IllegalStateException("无法解析 SFunction 对应的属性名", e);
    }
}
```

配合 `argThat` 使用：

```java
private static SFunction<Entity, ?> columnNamed(String property) {
    return argThat(column -> property.equals(propertyOf(column)));
}

verify(updateChain).set(columnNamed("status"), eq(PENDING.getCode()));
verify(updateChain).set(columnNamed("reason"), eq("本次填写的内容"));
```

解析失败要**抛异常**而不是返回 `null`——静默返回 null 会让 matcher 永不匹配，
`verify` 报的却是「没有期望的调用」，把人引向错误的排查方向。

## 分支改动的行覆盖率

单测报告第 4 节用例覆盖之后要写这个数。不要改 pom 把 JaCoCo 绑进构建，用命令行插件即可。`prepare-agent` 必须写在 `test` 前面，surefire 才会带上 agent。有失败也要出报告，所以加上 `maven.test.failure.ignore`。

```text
mvn -pl <被测模块> org.jacoco:jacoco-maven-plugin:0.8.12:prepare-agent test org.jacoco:jacoco-maven-plugin:0.8.12:report -Dmaven.test.failure.ignore=true
```

报告在 `<模块>/target/site/jacoco/jacoco.xml`。再和分支 diff 求交：

- 基线默认 `origin/master`（或 `origin/main`）。用 `git diff -U0 origin/master...HEAD -- *.java` 取出 `src/main/java` 的新增和修改行。
- 一行算进分母，当且仅当它既在 diff 里，又出现在 JaCoCo 的 `line` 节点上。注释、空行、import 没有 `line` 节点，不算。
- `ci > 0` 算已覆盖。失败用例在断言前执行过的行算已覆盖。
- 基线上已有、本分支没改的类（启动类、公共配置）在 JaCoCo 全量里，不在 diff 里，必须剔掉。不要直接抄 JaCoCo HTML 首页的整模块百分比。
- 同一分支还有别的需求时，只保留本需求相关的改动文件进这份报告的分母。类表要写到未覆盖的方法名。
- **无基线分支或 diff 为空时的回退**：若目录不在 git 仓库、无远端/基线分支（如评测复制到仓库外独立目录的 fixture），或给存量已合入代码补单测导致 `base...HEAD` 下 `src/main/java` 无 diff，在报告中写明原因，改为取「阶段 1 定性识别出的被测生产类」在 JaCoCo XML 中的 `line` 节点作为分母（仍剔除与本需求无关的其他类，不直接抄整模块百分比）。

用例范围写了不测的入口，覆盖率可以是 0。写明原因即可，不要为了百分比去补那批测试，也不要改开发代码。
