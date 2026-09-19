# Modeling Workbench

简体中文 | [English](README.en.md)

**从赛题到论文，让 AI 辅助建模有据可查。**

面向数学建模比赛的 **Codex / Claude Code 工作流**。提供官方赛题与附件，由 agent 按阶段完成问题拆解、模型比较、计算、复核和中英文 LaTeX/PDF 交付；你在三个关键节点审阅并决定是否继续。

**读题 → 比较模型 → 运行计算 → 独立复核 → 写论文 → 检查并交付 PDF**

- **模型经过比较再选定**：先试算候选方案，记录取舍依据，再进入正式计算。
- **论文数值有出处**：计算记录关联代码、数据和结果，代码修改后能发现旧证据失效。
- **交付包含可检查的材料**：中英文论文、源码与结果、复核记录，以及经过编译和逐页检查的 PDF。

工作流帮助组织和核验过程；模型是否合理、结论是否成立，仍需要结合题意与证据判断。

[快速开始](#快速开始) · [比赛支持](#比赛支持范围) · [架构与七个阶段](#3-七个阶段) · [完整走查](#6-一次完整走查) · [开发说明](#13-开发)

## 快速开始

**准备好 Codex 或 Claude Code，把官方赛题、附件和当届提交要求放进同一个文件夹。** 接下来复制两段提示词即可，无需先安装 Skill、填写契约或逐个运行脚本。

### 第一步：准备环境（首次使用）

在一个可写的本地目录中打开对话，发送：

```text
请下载或复用 https://github.com/Lucasuiii/modeling-workbench 到独立工具目录，
先检查已有仓库，不覆盖本地改动。完整读取仓库中的
.agents/skills/cumcm-workflow/SKILL.md，按说明检查 Python 3.10+、
Python 依赖、MATLAB 或 Python 计算后端、XeLaTeX 和 PDF 渲染工具。
需要安装或修改环境时，先列出变更并等我同意。
本次只准备环境，不初始化赛题；完成后报告工具目录、版本和缺失项。
```

### 第二步：开始建模（每道新题）

环境就绪后，**新开一个对话**，替换下面三处路径并发送。工具目录用第一步返回的路径；输出目录使用尚不存在的新目录，与工具和材料目录分开。

```text
请使用 Modeling Workbench 开始本次建模任务。
工作流工具目录：/绝对路径/modeling-workbench
官方材料目录：/绝对路径/赛题资料
新项目输出目录：/绝对路径/新项目

完整读取工具目录中的 .agents/skills/cumcm-workflow/SKILL.md。
先检查环境与官方材料，不覆盖已有内容；环境缺失则报告，不在此对话安装。
从材料识别比赛、年份、论文语言和提交要求，不明确时问我。
按 Skill 初始化并开始问题拆解，在模型选择、写论文前的结论、
最终交付三个节点等我明确确认。
```

**接下来你只需跟随阶段提示审阅材料。** 同一环境再次使用时可直接从第二步开始。中断后，提供项目输出目录并说“继续 cumcm-workflow”；已有项目应恢复，不要重新初始化。

<details>
<summary>路径、Windows 和环境问题</summary>

- **macOS**：路径例如 `/Users/你的名字/Documents/赛题资料`。
- **Windows 推荐 WSL2**：在 WSL2 中运行 agent 和工具，材料路径例如 `/mnt/c/Users/你的名字/Documents/赛题资料`；新项目可放在 `/home/你的WSL用户名/modeling-projects/2026B`。
- 路径须采用 **agent 执行环境**可见的格式。Python、计算后端和 XeLaTeX 也须在同一环境中可用。
- 原生 PowerShell 尚未经过端到端验证；本文后面的 Bash 示例不能直接照抄。
- 让 agent 检查并报告缺失依赖即可，无需预先手动配置整套工具。环境安装时间取决于现有依赖，首次 LaTeX 准备可能较久。
- 初始化会复制并固定官方材料的身份，不修改原材料目录；自主选题任务请提供官方主题与要求。

</details>

<details>
<summary>已安装 Skill？版本与调用名说明</summary>

可用 Codex 的 `$cumcm-workflow` 或 Claude Code 的 `/cumcm-workflow` 触发，仍需提供材料目录和新项目目录，并确认实际 Skill 路径及环境可用。

仓库名为 `modeling-workbench`，Skill 调用名、目录和 `.cumcm` 工作区格式保持不变。当前版本 **v0.6**；不支持旧于 v0.6 的工作区。此次多比赛扩展保留 CUMCM/中文默认值，现有 v0.6 工作区无需迁移。

</details>

## 比赛支持范围

从 CUMCM 国赛流程扩展而来，其他比赛可共用建模、计算、复核和中英文论文交付链。

| 比赛或任务 | 已提供的支持 | 需按当届要求适配 |
|---|---|---|
| CUMCM 国赛 | 完整流程，默认中文论文骨架 | 官方模板与提交要求 |
| 华为杯、MathorCup、电工杯及区域建模赛 | 通用建模与验证指导、中文 PDF 与源码交付 | 专用排版、附件和结果文件 |
| MCM/ICM、APMCM 等英文任务 | 英文写作指导、英文 PDF 与源码交付 | 摘要页、页数统计、附加文书 |
| 泰迪杯及其他数据分析任务 | 数据处理、评价指导，共用论文交付工具 | 结果表、数据字段和提交包 |
| 统计建模及自主选题任务 | 选题、数据可得性与研究设计指导 | 官方主题、数据来源与结论范围 |

**通用论文骨架不等于官方模板。** 当届官方要求优先；DOCX 导出与任意官方模板的自动转换尚未提供。比赛名称与论文语言由 agent 在论文阶段传入，不需要你手动运行初始化命令。详见[比赛适配指南](.agents/skills/cumcm-workflow/references/competition-adaptation.md)。

<details>
<summary>兼容性验证覆盖到哪里？</summary>

已验证中英文骨架的实际编译、渲染和打包，以及其他比赛的合成 finalizing 流程和原有关卡。这不代表逐赛事、逐年份的官方格式认证，也不代表已完成每类比赛的完整赛题求解验收。

</details>

---

## 1. 它解决什么问题

让模型自由发挥地做数模，典型失败不是"算错"，而是这五种：

| 失败 | 表现 | 本工作流的应对 |
|---|---|---|
| 答非所问 | 建了个漂亮模型，但没回答题目问的那个量 | 每个小问必须有 capability 负责，且带一个**可能失败**的验收检查 |
| 结论没有计算支撑 | 论文写了个数，但没有一次运行产生过它 | 结论只能引用成功的 official run，数值由脚本从输出里读回 |
| 代码和结论对不上 | 改完代码忘了重跑，论文还是旧数 | official run 绑定源码树快照，一改就报 stale |
| 越界宣称 | 在受限策略类里找到最优，写成"全局最优" | 强断言必须带 certificate 和适用范围 |
| 自说自话的评审 | "我检查过了" | 复核在独立上下文进行，独立性字段必须被正面声明 |

它**不**保证的：模型在数学上正确、全局最优、统计设计合理。检查通过只意味着"结构、来源、执行记录和已记录的评审边界是一致的"。

---

## 2. 两条规则

整个 v0.6 就是这两句话的展开。

### ① tooling 记录机器事实，agent 写语义判断

| 脚本观察并写入 | 你写 |
|---|---|
| argv、工作目录、起止时间、退出码、stdout/stderr | 这次运行是干什么的 |
| SHA-256、`sha256-tree-v1` 源码树快照 | 哪些文件是 formal input / claim-bearing output |
| 从 locator 读回的结果数值 | 结果的名字、单位、适用范围 |
| PDF 页数、PDF 哈希、逐页渲染图 | 版面能不能看的最终判断 |
| 编译日志里的 overfull / 未定义引用 / 缺字 / 字体错误 | 题意、模型、claims、论文正文 |

你永远不需要手算一个哈希。**如果某个改动会让 agent 把 SHA-256、退出码、页数或结果数值敲进 JSON，那个改动是错的**——去扩展记录器。

### ② 模型是后选的，而且选择要靠证据挣来

真实建模不是"先写对合同再执行"，而是：

```text
Problem Analysis
      │
      ▼
Model Design ─────► 候选 A / 候选 B
      │             · 为什么值得考虑（why_considered）
      │             · 用什么证据区分（discriminating_evidence）
      ▼
Computation ──────► 低成本 exploratory evaluation
      │             record_run.py --candidate CAND-A
      │             record_run.py --candidate CAND-B
      ▼
选择 A ───────────► status: selected
      │             decision_rationale 说明凭什么选它
      │             evaluation_run_ids 指向那两次探索运行
      ▼
A 做 official computation
      │             record_run.py --official
      ▼
Validation
```

这条链在 v0.6 里是**有结构、被检查**的，不只是一段建议：

- 恰好一个候选可以是 `selected`（`MODEL-E013`）；
- 被选中的候选必须引用真的评估过它的运行（`MODEL-W014`）；
- 选中或淘汰都要有理由（`MODEL-E014`）；
- 候选说不出"用什么区分"会被标出来（`MODEL-W012`）；
- `cumcm_check.py` 在报告里打印整张对比表（`model_candidates`）。

`working` 期这些是 warning，冻结时变成 error。只有一个候选是允许的（只提示 `MODEL-W007`）——本工作流不逼你凑候选，它只是不让你声称一场没做过的比较。

---

## 3. 七个阶段

```text
intake → problem-analysis → model-design → computation → validation → paper → delivery
```

| 阶段 | 做什么 | 产出 | 谁写 |
|---|---|---|---|
| `intake` | 把官方题目/附件/格式文件复制进来并按字节固定身份 | `problem/SOURCE_MANIFEST.json` | `init_project.py` |
| `problem-analysis` | 拆小问、抽事实（带页/表/单元格出处）、标歧义、定验收目标 | `PROBLEM_FACTS.json`、`TASK_CAPABILITIES.json` | agent |
| `model-design` | 提出候选、说明区分证据；选定后冻结正式合同 | `MODEL_CONTRACT.json` | agent |
| `computation` | 探索评估候选 → 选定 → 正式实现并运行 | `runs/*/RUN_MANIFEST.json`、`RESULTS_INDEX.json` | `record_run.py`、`index_result.py` |
| `validation` | 打包证据交给独立上下文复核，落成 claims | 复核包/结果、`CLAIM_LEDGER.json` | 脚本打包，agent 写 claims |
| `paper` | 选论断、选表达、写作、编译、逐页 QA | `PAPER_PLAN.json`、LaTeX、`PAPER_QUALITY_REPORT.json` | agent + `init_latex_paper.py`、`record_compile.py` |
| `delivery` | 对照官方规则冻结提交版本 | `COMPILE_RECEIPT.json`、`DELIVERY_MANIFEST.json` | `record_compile.py` + agent |

原则上 modeling、computation、validation、paper 分别在**不同的 fresh task** 里做。跨职责只通过四个 handoff 传递，新 task 先读 handoff、再按指针补读，不扫描整个工作区：

```text
modeling-computation   computation-validation   validation-paper   paper-delivery
```

handoff 只带路径、角色、摘要和一个 upstream digest；不带完整日志、失败运行、调试历史或旧复核对话。任一上游产物变了，handoff 立刻 stale，必须重建。

---

## 4. 证据模型

### 三个等级

| 等级 | 含义 | 是否阻断 |
|---|---|---|
| **P0 / hard invariant** | 数据或计算错误、答非所问、关键结论无证据、代码与结果不符、provenance 失效、伪造审批或复核、最终版本不一致 | **阻断** |
| **P1 / warning** | 假设强、baseline 弱、验证或敏感性不足、拟合有限、章节单薄；**以及探索运行的一切问题** | 可见，不阻断 |
| **P2 / suggestion** | 措辞、排版、可选图表、额外实验 | 不进入 gate |

### 正式计算的唯一链条

```text
RESULTS_INDEX.json → 被引用的 run_id → official_run:true 且 exit 0
                   → 当前有效的 sha256-tree-v1 源码快照
                   → locator 指向该运行声明的 claim_bearing_output
```

computation→validation handoff、独立复核包、paper→delivery handoff 三个消费者**共用同一个解析器**。任何一环缺失、失败、非 official 或 stale，三处一起明确失败——不会一个忽略、另一个才报错。

### 探索运行是一等公民

```bash
record_run.py --project <p> -- python3 code/try.py
```

零 flag，产出一份合法的 `official_run: false` 记录。它被记录、不被信任、**永不阻断**：断言失败、非零退出、缺日志、缺 capability，全都是 warning。它也不进入阶段批准范围——新增探索运行不会让已批准的 computation 失效。

这是有意的：Deferred Model Selection 的全部收益都来自"试算便宜"。

### 运行是追加的，证据是冻结的

`--rerun` **不覆盖**，它追加一个新运行（`RUN-Q1-001` → `RUN-Q1-002`），`parent_run_id` 指向被取代的那个。父运行连同日志原封不动留下——"改代码之前那次正式运行算出了什么"永远答得上来。

每次运行还会把 `--source` 和 `--output` **冻结**进自己的目录，镜像原来的相对路径：

```text
runs/RUN-Q1-002/
├── RUN_MANIFEST.json
├── stdout.log  stderr.log
├── source/code/solve.py        ← 执行时那一版代码的副本
└── outputs/results/q1.json     ← 那次产出的副本，locator 指这里
```

冻结副本不可变，所以被保留的运行永远可验证。而"改了代码却没重跑"这条最有价值的检查并没有丢——它改成比对**冻结副本与当前活文件**：

```
ERROR RUN-E020  the working tree no longer matches this official run: code/solve.py
                remediation: record_run.py --rerun RUN-Q1-001 --official
```

被取代的运行豁免这条（它当然不一样，这正是你取代它的原因）；反过来，改动冻结副本本身是另一类失败 `RUN-E021`（证据被篡改）。

`superseded` 由 `parent_run_id` 链**推导**，绝不回写旧 manifest——回写会改变它的哈希，把已经绑定它的 accepted decision 全部打成 stale。结果仍指着被取代的运行时报 `RESULT-E017`，用 `index_result.py --follow-lineage` 显式重新指向：换哪次运行支撑结论是语义判断，不能让工具偷偷替你做。

`problem/official/` 下的 input 就地取哈希（不可变契约已保护，且附件可能很大）；其余 formal input（`data/cleaned.csv` 这类会被重新生成的）同样冻结，有体积上限。

还有两条记录期的硬规则，都是防伪造：

- **不能冒领输出**。执行前后比对每个 declared output 的 mtime。一个 exit 0 却没写文件的程序，否则会把上一轮的结果连同真哈希一起冻结成自己的 claim 证据——真哈希、假出处。这种情况 `record_run.py` 直接拒绝写 manifest 并指出是哪个文件。
- **不能继承判决**。`--rerun` 永不继承父运行的 assertions。新代码没有被旧的 `pass` 验证过，继承它等于凭空给 `MODEL-E009`（冻结模型必须有已执行的验证）喂证据。
- **手打的判决不算已验证**。`--assert x=pass` 记为 `declared`（调用者备注），`--assert-file` 读程序自己写出的判决、记为 `recorded`。只有 `recorded` 能满足冻结模型的 `verification_plan`；official run 全是手打断言时报 `RUN-W003`。
- **证据不能在脚下移动**。声明的源码和 formal input 在执行前取哈希、执行后复核——冻结发生在命令退出之后，运行中被改过的文件会被冻结成"运行从未读过的东西"。

另外 `RUN-E024` 真正落实了 single-backend：同一 capability 不能同时存在 MATLAB 和 Python 的当前 official run（working 是 warning，冻结时是 error）。随机模拟用 `--seed` 记录种子。

**只有成功的 official child 才构成取代**：失败或探索性的重跑什么也没替代。checker、handoff、复核包和 delivery 共用同一个解析器，所以"当前正式运行"四处含义一致。claim/figure 仍引用被取代运行时报 `CLAIM-W020`/`FIGURE-W013`。

---

## 5. 两个旋钮

v0.6 没有 profile。只有：

| 旋钮 | 取值 | 决定 |
|---|---|---|
| `mode`（存在 state 里） | `working` / `finalizing` | **什么必须完整** |
| `--gate-mode` | `preflight` / `enforce` | **人工门禁是否计入阻断** |

- `working`：草稿模型合同即可、`CROSS_QUESTION_LEDGER.json` 可选、阶段排序只是 warning。官方输入保护、真实执行、精确 locator、非伪造照样强制。`preflight` 显示待审查而不阻断探索；`enforce` 在两种模式都要求人工确认。正式运行和论文入口也检查对应确认。
- `finalizing`：完整模型合同（且 `verification_plan` 要对应到官方运行真的记录过的断言）、目标及上游阶段全部 `passed`、当前 accepted decision 与 snapshot、fresh handoff、独立复核、PDF QA、delivery 绑定。

阶段状态只有四个：`not_started` / `in_progress` / `passed` / `needs_revision`。

三个必需人工确认点是模型选择、写论文前的结论、最终交付。展示当前材料并收到明确回复后，用 `record_decision.py --decision accepted --confirm-human`，指定 `--stage`、`--task-turn-ref` 和 `--summary`；命令自动填入现有确认字段并推进状态。技术阶段检查通过后省略 `--confirm-human`。模型自审不算人工确认，记录仍依赖如实引用用户回复。

---

## 6. 一次完整走查

```bash
S="$PWD/.agents/skills/cumcm-workflow/scripts"  # 在仓库根目录设置
```

**① 初始化**（对话里直接说"用 cumcm-workflow 从 /path/to/2026B 初始化"即可，agent 会替你跑）

```bash
python3 $S/init_project.py --project ~/cumcm/2026B --project-id CUMCM-2026-B --official /path/to/2026B
```

官方文件被复制进 `problem/official/` 并记录哈希；原目录不被修改。

**② 拆题**：agent 写 `PROBLEM_FACTS.json`（每条事实注明来源文件与位置）和 `TASK_CAPABILITIES.json`（每个小问一个负责人 + 可能失败的验收检查）。

**③ 提候选**：agent 在 `MODEL_CONTRACT.json` 里写 2 个候选，各带 `why_considered` 和 `discriminating_evidence`。

**④ 探索评估**：

```bash
python3 $S/record_run.py --project <p> --candidate CAND-A -- python3 code/try_a.py
python3 $S/record_run.py --project <p> --candidate CAND-B -- python3 code/try_b.py
python3 $S/cumcm_check.py --project <p> --stage model-design --gate-mode preflight
```

**⑤ 选定并正式运行**：把胜者置 `selected` 并写理由，然后

```bash
python3 $S/record_run.py --project <p> --official \
  --capability CAP-Q1-001 --source code/solve.py \
  --input data/q1.csv:formal --output results/q1.json:claim \
  --assert-file results/assertions.json -- python3 code/solve.py

python3 $S/index_result.py --project <p> --result-id RES-Q1-001 --run RUN-Q1-001 \
  --locator 'results/q1.json#/minimum_cost' --name "最小成本" --unit CNY \
  --scope "仅限声明的候选集"
```

数值从 locator 读回，不经过你的手。

**⑥ 改了代码？** 追加一次继任运行，父运行原封不动留下：

```bash
python3 $S/record_run.py --project <p> --rerun RUN-Q1-001 --official   # 产出 RUN-Q1-002
python3 $S/index_result.py --project <p> --follow-lineage
```

**⑦ 冻结与复核**：

按需读取[数学机制验证指导](.agents/skills/cumcm-workflow/references/mechanism-validation.md)，将适用风险接入验证计划、程序断言和独立复核；复核包冻结同一份参考，不增加全题通用检查清单。

```bash
python3 $S/set_mode.py --project <p> --mode finalizing
python3 $S/build_handoff.py --project <p> --transition computation-validation
python3 $S/build_independent_review_package.py --project <p>
```

脚本到这里**主动停下**：你需要把复核包交给另一个 task 或另一个人，拿回结构化结果。

**⑧ 论文**：

```bash
python3 $S/build_handoff.py --project <p> --transition validation-paper
python3 $S/init_latex_paper.py --project <p> --competition-year 2026 \
  --title "<真实题目相关标题>" --keywords "<真实对象; 模型; 方法>"
python3 $S/record_compile.py --project <p> --update-quality
python3 $S/paper_visible_text_check.py --project <p> --pdf paper/main.pdf
```

`record_compile.py` 会把每一页渲染到 `.cumcm/tmp/pages/`——**然后真的去看那些图**。 编译回执记录引擎实际读取的项目源码和图片，源码 ZIP 使用同一集合。日志判断只看最后一遍；刷新机器字段保留原有视觉发现，旧 PDF 的检查仍绑定旧版本，需要重新审查。渲染不可用不会沿用旧页记录，失败重编译也不会留下当前成功回执。

**⑨ 交付**：按项目目录打包，验包检查已声明文件的缺失和过期；不代替解压后的运行检验。刷新不改官方来源，无变化不重写清单。

```bash
python3 $S/build_handoff.py --project <p> --transition paper-delivery
python3 $S/refresh_evidence.py --project <p> --only delivery --package
python3 $S/cumcm_check.py --project <p> --stage delivery --gate-mode enforce
```

---

## 7. 迭代与 scoped redo

回改上游不需要手动改 `state.json`：

```bash
python3 $S/record_decision.py --project <p> --stage model-design \
  --decision revision_requested --decision-id DEC-007 \
  --reviewer <name> --task-turn-ref <ref> --summary "Q2 模型不符合观测区间"
```

它把该阶段及全部下游置为 `needs_revision`、删掉下游 snapshot、使相关人工确认失效，并把 `current_stage` 移回去。下游处于 `needs_revision` 是重开后的**正常状态**，不是错误。

改完之后先问"到底要重做什么"：

```bash
python3 $S/plan_redo.py --project <p> --changed code/solve_q2.py
```

```text
computation
  - re-run RUN-Q2-003: record_run.py --rerun RUN-Q2-003 --official (appends a successor)
  - re-point results to the successor: index_result.py --follow-lineage (RES-Q2-001)
validation
  - targeted re-review covers: F-003
  - rebuild the package: build_independent_review_package.py --review-mode auto --refresh
paper
  - rewrite or re-review: paper/sections/40_q2.tex
delivery
  - recompile and rebind: record_compile.py --update-quality

not affected (do not redo):
  computation: RUN-Q1-001
  paper: paper/sections/20_q1.tex
```

确定性检查本身很便宜，所以它继续**无条件全查**。被 scope 的是重跑、重复核、重写这三件真正贵的事。

---

## 8. 独立复核

审查从当前题目的风险出发，检查任务覆盖、模型与求解有效性、验证辨别力和结论范围；按问题选择检验，不套用固定实验清单。第一次 review 是 full 且上下文分离的。复核包只复制正式结果对应的 canonical evidence，并声明 `context_excluded`——打包器**实际排除**了 originating task transcript、debug history、failed runs、prior review prose。它不声称"reviewer 心里没有结论"，因为那不可验证。

结果模板的四个独立性字段初值是 `null`，必须由 reviewer 或用户正面声明；留 null 直接失败（`IREVIEW-E027`）。两个 task ref 必须不同，但这只是防复制粘贴的护栏，**不是独立性证明**。

Verdict：`accepted` / `accepted_with_concerns` / `revision_required` / `inconclusive`。只有开放 P0 才允许 `revision_required`。full review 出现 P0 后，下一次打包默认 targeted re-review，包内生成自包含的 `TARGETED_FINDINGS.json`，reviewer 不需要读旧 review 全文。

---

## 9. MATLAB 还是 Python

默认 `{"preferred":"matlab","fallback":"python","selection":"auto"}`。MATLAB 只是同等条件下的 tie-break，不是强制。判断依据是任务本身：数值线性代数、优化、ODE/PDE、信号处理偏 MATLAB；数据清洗、CSV/Excel、机器学习、已有 Python 代码偏 Python。

检测顺序：项目 `implementation.matlab_executable` → PATH 里的 `matlab` → macOS `/Applications/MATLAB_R*.app/bin/matlab`。preferred 不可用可以 fallback 并记录原因；任务声明的 `required_backend` 不可用则直接报错，不静默切换。

**一旦选定，只正式实现并运行这一种。** 除非用户明确要求跨语言互验，否则不做 parity 实现。

---

## 10. 产物清单

```text
<project>/
├── .cumcm/
│   ├── state.json              # 阶段、模式、后端偏好
│   ├── decisions.jsonl         # 追加式人工决策（唯一的正式批准来源）
│   ├── snapshots/<stage>.json  # 由 accepted decision 自动派生
│   └── tmp/pages/              # record_compile 渲染的逐页 PNG
├── problem/official/           # 官方输入，只读
├── problem/SOURCE_MANIFEST.json
├── analysis/                   # PROBLEM_FACTS / TASK_CAPABILITIES（+ 可选笔记）
├── model/MODEL_CONTRACT.json   # 含候选与选择记录
├── code/                       # 你的实现
├── runs/<id>/                  # RUN_MANIFEST + stdout/stderr（脚本写）
├── results/RESULTS_INDEX.json  # 脚本写
├── validation/                 # 复核包、复核结果、CLAIM_LEDGER
├── paper/                      # PAPER_PLAN、LaTeX、QA sidecars
├── delivery/                   # COMPILE_RECEIPT、DELIVERY_MANIFEST
└── handoffs/<transition>/HANDOFF.json
```

需要 agent 手写的契约只剩 9 个：`PROBLEM_FACTS`、`TASK_CAPABILITIES`、`MODEL_CONTRACT`、`CROSS_QUESTION_LEDGER`（可选）、`CLAIM_LEDGER`、`FIGURE_MANIFEST`（可选）、`PAPER_PLAN`、`PAPER_QUALITY_REPORT`、`INDEPENDENT_REVIEW_RESULT`。其余全部由脚本产生。

---

## 11. Hard invariant 一览

下列问题在任何模式下都阻断：

官方输入被修改或身份不一致 · 把模拟数据当观测数据 · claim-bearing 计算没有成功的 official run · 源码快照/formal input/claim-bearing output 漂移 · result locator 错误或索引值与输出不一致 · 复核包或 handoff stale · 伪造人工审批或独立复核 · validation/paper 存在开放 P0 · 最终 PDF 不可读或版本不一致 · PDF 未绑定已批准 QA 与 editable source · 字体/缺字检查失败 · PDF/LaTeX/计算程序三类交付不完整

---

## 12. 在 Codex 和 Claude Code 里用

唯一 canonical 树是 `.agents/skills/cumcm-workflow/`（SKILL.md、references、schemas、scripts、assets）。

- **Codex**：仓库内 `.agents/skills/` 自动可见，`agents/openai.yaml` 提供展示名和默认提示词。用 `$cumcm-workflow` 触发。
- **Claude Code**：仓库内用 `/cumcm-workflow` 或明确要求“使用 cumcm-workflow”。`.claude/skills/cumcm-workflow/SKILL.md` 只链接到正式 Skill，链接相对于路由文件定位，不依赖当前工作目录。根目录 `CLAUDE.md` 明确区分“解题”和“维护仓库”；工程规则仅适用于后者。

在任意目录使用 Claude 个人 Skill，并随仓库更新保持同步：从仓库根目录运行下列命令，将**完整 canonical 目录**链接到个人 Skill 目录。目标已存在时先检查现有安装，不要覆盖。

```bash
mkdir -p ~/.claude/skills
ln -s "$PWD/.agents/skills/cumcm-workflow" ~/.claude/skills/cumcm-workflow
```

保留仓库位置，移动后需要重建链接。若希望脱离仓库使用，可复制完整 `.agents/skills/cumcm-workflow/`；副本不会自动同步，升级时需要重新同步整个目录。不要只复制 `.claude/` 中的路由。

两端读取同一套阶段规则。脚本路径从实际 Skill 目录取得绝对路径；脚本通过 `Path(__file__)` 定位 schema 和 assets。入口测试验证路由链接、完整 Skill 在异地目录的脚本启动及元数据一致性。

---

## 13. 开发

```text
.agents/skills/cumcm-workflow/   # canonical
.claude/skills/cumcm-workflow/   # Claude Code 路由
CLAUDE.md                        # 改仓库时的约定
docs/                            # 架构、合同、provenance、限制、v0.6 设计
tests/  examples/  .github/workflows/ci.yml
```

```bash
python3 -m pip install -r requirements-ci.txt
python3 -m unittest discover -s tests -p 'test_*.py' -v
python3 -m compileall -q .agents/skills/cumcm-workflow/scripts tests
```

CI 在 Python 3.10 与 3.13 上跑契约测试；另有一个装了 texlive 的 job 用**真实 xelatex 编译**跑通 recorder 链路。

不向下兼容：v0.6 拒绝任何 `schema_version` 不是 `0.6.0` 的契约，仓库里也不再保留迁移脚本。旧工作区请用官方文件重新初始化。

---

## 14. 局限

- 检查通过不代表模型、统计设计或全局最优性被证明。
- fresh context 降低污染，但不能证明 reviewer 独立或正确；同模型的 fresh task 仍然相关。
- digest 证明文件身份，不证明代码实现了它声称的数学。
- 冻结后的模型合同可能退化成"对已写好代码的事后描述"。机器只能检查 `verification_plan` 是否对应到已记录的断言；剩下的写在 `REVIEW_REQUEST.md` 的失败类清单里，交给 fresh-context reviewer。
- `plan_redo.py` 只能沿已记录的 ID 图推断，看不到未声明的隐式依赖。
- 版面检查来自编译日志，发现不了"图里文字太小"。逐页 PNG 已经渲染好了，仍然需要人去看。
- 记录器只在被调用时记录：绕过 `record_run.py` 直接跑仍可能产生无证据的结果，检查器只能发现"没有 official run 支撑"。

完整列表见 [已知限制](docs/limitations.md)。

[MIT License](LICENSE)
