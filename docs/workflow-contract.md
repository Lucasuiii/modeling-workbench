# 工作流合同

| 职责 | Hard invariant（阻断） | Non-blocking concern |
|---|---|---|
| Intake | 官方输入保持不变且身份正确 | 可选来源元数据的完善 |
| Modeling | 每个官方小问都有 capability 负责，且有可失败的验收检查；模型范围不与题意冲突；冻结时候选比较必须收敛到恰好一个 selected 且有理由 | 草稿期的模型广度；working 期尚未归属的 capability；候选缺少区分证据 |
| Computation | 一个成功 official run、当前 source snapshot、formal input/output 和精确 result locator | 探索运行的一切问题（失败、缺日志、断言不过）；更多诊断或性能优化 |
| Validation | Fresh package、没有开放 P0、claim 有证据和适用范围、独立性字段被正面声明 | P1 验证/敏感性/泛化 concern；P2 suggestion |
| Paper | 回答每个小问；不发明结果、不泄露内部元数据；没有开放 paper P0；版面失败项来自编译日志 | 图表密度、章节强度和可选润色 |
| Delivery | 精确的 reviewed PDF、当前 editable source snapshot、成功编译、字体/缺字检查、官方格式审查和三类交付角色 | 非关键展示优化 |

## Gate 语义

两个旋钮：`mode`（working / finalizing）与 `--gate-mode`（preflight / enforce）。没有 profile。

在 `working` 模式中，草稿模型合同和不完整的下游产物都可以继续。`finalizing` 的 `enforce` 要求目标阶段及全部上游为 `passed`，并由当前 accepted decision 和派生 snapshot 覆盖。编辑 state 不能代替 decision。

自动错误分为两类：

- hard invariant：在 working/finalizing 中都不能降级；
- finalizing completeness：working 中可以暂缺，进入 finalizing 后必须满足。

Warning 和 suggestion 会进入报告，但不改变通过状态。

## 运行与继任语义

| 规则 | 含义 |
|---|---|
| `RUN-E020` | 活文件与该 official run 的冻结源码不同（被取代的运行豁免） |
| `RUN-E021` | 冻结证据本身缺失或被改动 |
| `RESULT-E017` | 正式结果仍引用被后续运行取代的运行 |
| `RUN-E007`（inputs，被取代运行） | 降为 warning：官方目录下的 input 就地取哈希，历史运行读过的数据可以合法地变了 |
| `CLAIM-W020` / `FIGURE-W013` | claim/figure 仍引用被取代的运行 |
| `RUN-W003` | official run 的断言全部是命令行手打的，没有一条是运行自己写出来的 |
| `RUN-E024` | 同一 capability 存在多个后端的当前 official run（working 为 warning） |

记录期的两条硬规则（`record_run.py` 直接拒绝写 manifest）：

- **不能冒领输出**：执行前将旧 claim 输出和 `--assert-file` 文件移入新 run 的 `previous_outputs/`，要求本次重新生成非空常规文件。仅 touch 不能复用旧字节，重新计算得出相同字节可接受。缺失/空文件时恢复旧文件并拒绝 manifest；备份保留。intermediate/diagnostic 仍仅用 mtime 提醒。
- **不能继承判决**：assertions 永不从父运行继承。新代码没被旧的 `pass` 验证过，继承它等于给 `MODEL-E009`/`MODEL-W010` 喂造假证据。
- **不能手打判决充当已验证**：`--assert x=pass` 记为 `source: "declared"`（调用者的备注），`--assert-file` 读程序自己写出的判决，记为 `source: "recorded"`。只有后者能满足冻结模型的 `verification_plan`。
- **证据不能在脚下移动**：声明的源码与 formal input 在执行前取哈希、执行后复核；冻结发生在命令退出之后，运行中被改过的文件会被冻结成"运行从未读过的东西"，直接拒绝记录。

`--rerun` 追加而不覆盖；supersession 从 `parent_run_id` 链推导，不回写旧 manifest。**只有成功的 official child 才构成取代**——失败或探索性的 child 什么也没替代，让它退休父运行会把唯一可用的证据作废。一个父运行有多个成功 official child 时属于 ambiguous；必须用 `--run-id` 明确选择分支，不自动选最新。

checker、computation handoff、独立复核包和 paper→delivery 共用 `canonical_evidence.resolve_official_computation`，所以"当前正式运行"在四处含义一致，不会出现 checker 拦住而 builder 照样打包的情况。重新指向结果必须用 `index_result.py --follow-lineage` 显式进行。

被取代的运行仍然是 `official_run: true`——它当时确实是正式运行。它只是不再是当前结论的依据。

## 候选与选择语义

`components[].candidates` 让"选了 A"成为可核对的链条而不是一句声明：

| 规则 | 含义 | working | finalizing |
|---|---|---|---|
| `MODEL-E013` | 必须恰好一个候选 `selected` | warning | error |
| `MODEL-E014` | `selected`/`rejected` 必须有 `decision_rationale` | warning | error |
| `MODEL-W014` | `selected` 必须引用评估过它的运行 | warning | error |
| `MODEL-W012` | 候选应说明 `discriminating_evidence` | warning | warning |
| `MODEL-E015` | 引用的评估运行必须存在 | error | error |
| `MODEL-W016` | 被引用的运行应当用 `--candidate` 声明过它评估了谁 | warning | warning |
| `MODEL-W007` | 冻结时只有一个候选 | warning | warning |

只写一个候选是允许的：本工作流不逼你凑候选，它只是不接受一场没发生过的比较。

## 模型冻结语义

`working` 只要求 `model_id` / `capability_ids` / `method` / `scope`。进入 `finalizing` 才要求 `variables` / `inputs` / `outputs` / `verification_plan`，且：

- 该 component 覆盖的 capability 必须至少有一个 official run 记录过断言，否则 `MODEL-E009`；
- `verification_plan` 里对不上任何已记录断言名的条目产生 `MODEL-W010`。

能力归属（`CAP-E008`、`CAP-E009`）在两种模式下都是 error，因为"答非所问"不随模型换代而消失。

## Review 语义

Independent review 从 full pass 开始。如果返回开放 P0，下一轮默认 targeted re-review。`accepted_with_concerns` 足以进入 paper。

Targeted result 不必重复 full review 的 P1，但 validation→paper handoff 会沿结构化 lineage 取每个 finding 的最新状态。

复核包声明 `context_excluded`（实际排除的先验推理），而不是声称 reviewer 没有结论。结果模板的四个独立性字段初值为 `null`，必须被正面声明，否则 `IREVIEW-E027`。同一上下文不能满足 independent review；different model 或 human 也只表示 independence evidence 更强，不构成数学证明。

所有正式源码消费者采用同一链：`RESULTS_INDEX.json` → referenced successful `official_run: true` → current source snapshot。缺失、失败、non-official 或 stale 均为明确错误。

## 变化与重做范围

确定性检查始终完整运行到目标阶段。需要被 scope 的是昂贵动作——重跑、重复核、重写——由 `plan_redo.py` 沿 ID 图反向遍历得出，并同时列出**不受影响**的 run、finding 和 section。v0.5 的 `cosmetic/local/semantic/claim_changing/global` 分类已删除。

正式证据消费者统一由 canonical resolver 校验源码快照、全部 formal input 与 claim-bearing output 的实际 SHA256。入口仅接受可识别的直接 Python 脚本或 MATLAB `run('path.m')` 调用，`--source` 不能替代执行入口。Python runtime 来自实际命令解释器的运行前探测；seed、依赖和 toolbox 为声明元数据，rerun 保留 seed/toolbox 声明但不继承断言。

## 决策写入与失败定位

`record_decision.py` 在 POSIX 使用 `flock`、原生 Windows 使用 `msvcrt` 跨进程锁。锁覆盖编号分配、checkpoint 检查、追加决策日志、快照和状态写入；正常退出、异常退出由显式释放或进程关闭解除锁。这不会改变人工确认要求，也不是跨文件崩溃恢复协议。

`RUN-E008` 报告失败断言在数组中的序号（从 1 开始）与名称；无名称的条目标为 `unnamed`。消息不展开断言 `details`，名称中的不可打印字符被替换并限制显示长度。正式 run 的失败仍为 error，探索 run 仍为 warning；诊断更具体不代表检查放宽。

提交检查严格解码 UTF-8 JSON 与显式指定为 UTF-8 的 Poppler 输出。无法解码时报告失败，不通过忽略或替换字符绕过身份信息检查。平台验证范围见[已知限制](limitations.md#平台与验证边界)。
