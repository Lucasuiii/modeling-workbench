# 架构

v0.6 把可恢复状态保存在 workspace 文件中，把"编排任务"与"具体工作产物"分离，并把**机器事实的产生**从 agent 手里移交给脚本。

```text
orchestrator
  -> modeling artifacts（working 期是草稿合同 + 候选比较）
  -> modeling-computation handoff
  -> 单一选定后端：exploratory runs 评估候选 ⇄ 模型回改 -> 选定 -> official run（record_run.py）
  -> computation-validation handoff + review package
  -> 有边界的 independent validation
  -> validation-paper handoff
  -> fresh paper task
  -> paper-delivery handoff
  -> compile receipt（record_compile.py）+ 三类交付物
```

## 职责与状态机

顶层状态机保留七个阶段：

```text
intake -> problem-analysis -> model-design -> computation
       -> validation -> paper -> delivery
```

实际职责归并为 orchestrator、modeling、computation、validation、paper 和 delivery。Independent review 属于 validation gate，不是一个可以由主任务自行批准的新阶段。

阶段状态只有四个：`not_started`、`in_progress`、`passed`、`needs_revision`。

状态机不再假设单向前进。`record_decision.py --decision revision_requested` 是 reopen 原语：它把目标阶段及全部下游置为 `needs_revision`，删除对应 snapshot，并把 `current_stage` 移回去。下游处于 `needs_revision` 是重开后的正常状态；只有下游仍标 `passed` 才是矛盾（`STATE-E008`）。

## 模型选择的位置

模型不是在 model-design 里定下来的，而是在 model-design 里**摆开**、由 computation **裁决**：

```text
model-design   候选 A / 候选 B + 各自的 why_considered 与 discriminating_evidence
computation    record_run.py --candidate 对每个候选做低成本探索评估
model-design   恰好一个候选 status=selected，decision_rationale 引用那些运行
computation    只有选中的模型才拿到 record_run.py --official
validation     独立复核看到的是这条完整链，而不是一个凭空出现的模型
```

这条链由 `check_model_candidates` 检查，`cumcm_check.py` 的报告里以 `model_candidates` 呈现整张对比表。它不判断哪个候选更好——那是数学判断；它只保证选择是对着记录下来的证据做的。

## 两种运行模式

只有两个旋钮：state 里的 `mode` 决定"什么必须完整"，`--gate-mode` 决定"人工门禁是否计入阻断"。v0.5 的 `strict`/`sprint` profile 已删除。

- `working`：维护官方输入保护、真实执行、结果定位和关键 provenance；接受草稿模型合同，允许下游产物不完整，阶段排序只是 warning。
- `finalizing`：要求冻结的模型合同（含可被断言支撑的 verification plan）、目标及上游阶段均 `passed`、当前 accepted decision、stage snapshot、fresh handoff、独立复核和精确的最终版本绑定。

修改 state 字段不能代替人工 decision。

## 运行的生命周期

运行是追加的：`--rerun` 产出 `RUN-Q1-002` 并把 `parent_run_id` 指向 `RUN-Q1-001`，父运行连同日志原封不动保留。每次运行把声明的源码和输出冻结进 `runs/<id>/{source,outputs}/`，镜像原相对路径并对副本取哈希，因此被保留的运行永远可验证，`output_locator` 指向的也是不可变文件。

冻结不等于放弃漂移检测——检查器改为比对冻结副本与活文件：

| 情形 | 规则 | 含义 |
|---|---|---|
| 活文件与冻结副本不同（未被取代） | `RUN-E020` | 工作区走远了，需要重跑 |
| 冻结副本本身被改动 | `RUN-E021` | 证据被篡改 |
| 被取代的运行与活文件不同 | 不报 | 这正是取代它的原因 |
| 正式结果引用被取代的运行 | `RESULT-E017` | 用 `--follow-lineage` 显式重新指向 |

supersession 由 `parent_run_id` 链推导，不回写旧 manifest：回写会改变其哈希，令所有绑定它的 accepted decision 失效。

计算检查、结果索引和返工计划共用正式运行的成功条件及父子关系。数值结论标为 `reproduced` 时，验证器会从两个运行各自冻结的输出读值，按声明的容差比较。新执行的隔离程度和容差的数学意义由复核者判断。见[复现比较](../.agents/skills/cumcm-workflow/references/05-validation.md#reproduced-claims)。

## 机器事实的边界

这是 v0.6 最重要的架构约束：

| tooling 记录 | agent 写 |
|---|---|
| argv、cwd、时间、exit code、stdout/stderr | purpose、capability 归属、哪些文件是 formal input / claim-bearing output |
| SHA-256、`sha256-tree-v1` 源码树 | 模型、假设、claims、论文计划与正文 |
| locator 取出的结果数值 | 结果的 name / unit / scope / 验收含义 |
| PDF 页数、PDF 哈希、逐页渲染 | 版面是否可读的最终判断 |
| 编译日志的 overfull / undefined ref / missing glyph / font error | 内容评审结论 |

记录器只观察不判断：不猜 outputs、不自动提升 official、不替你选择哪个 run 支撑哪个 result。

## Snapshot 与 Handoff

Accepted decision 的 artifact scope 是 stage snapshot 的来源，脚本自动生成。computation 阶段的 scope 只包含 official run 及其源码快照——探索运行不进入正式批准范围，因此新增或修改探索运行不会让已批准的阶段失效。

Handoff 复用少量阶段产物并计算 upstream digest。普通 handoff 只保存路径、角色、摘要和 digest。Independent review package 是例外：reviewer 可能在另一个 task 或 workspace 工作，所以复核包复制正式结果对应的 canonical evidence，并单独绑定 package/upstream digest，同时声明 `context_excluded`——它实际排除了哪些先验推理。

`workflow_checks.py` 始终完整重查到目标阶段。它很便宜，所以不做增量跳过；报告里的 `stages_with_current_decision` 陈述"哪些阶段的 accepted decision 仍对应当前文件"，不代表跳过了任何检查。真正需要 scope 的是重跑、重复核和重写，由 `plan_redo.py` 按 ID 图反向遍历给出。

## 计算与论文绑定

正式计算把一个选定的 MATLAB/Python 实现绑定到 source-tree snapshot、成功命令、formal inputs、claim-bearing outputs、日志、断言和结果索引，全部由 `record_run.py` 观察写入。同一正式任务默认不建立双语言 parity 实现。Computation handoff、独立复核包和 paper→delivery 通过同一 `RESULTS_INDEX → official run → source snapshot` resolver 解释正式源码。

最终编译由 `record_compile.py` 完成：compile receipt 把最终 PDF 绑定到实际参与编译的 editable LaTeX source-tree snapshot；paper→delivery handoff 同时携带该绑定、正式计算源码指针和官方材料角色。
