# 已知限制

- 跨比赛扩展目前属于 Skill 指导层：新增比赛适配、自主选题、题型与数据建模、中英文写作指导，没有修改状态机、schema、记录器或关卡。`init_latex_paper.py` 和模板 schema 仍固定 CUMCM，交付仍要求 LaTeX/PDF；没有自动英文骨架或 DOCX 导出回执。其他比赛可复用前面的分析、计算和复核方法，但不能据此声称完整自动交付已经适配，不能把赛事改标为 CUMCM 来通过检查。具体边界见 [比赛适配](../.agents/skills/cumcm-workflow/references/competition-adaptation.md)。

- v0.6 检查通过不代表模型、统计设计或全局最优性已经被证明。
- v0.6 不向下兼容，也不提供迁移脚本：旧工作区用官方文件重新初始化。
- Fresh context 能减少上下文污染，但不能证明 reviewer 真正独立；origin/reviewer task ref 仍是用户和工具记录的证据。
- 同一模型的 fresh task 仍具有相关性，只能标记为 context-separated model correlated。
- 后端选择依据声明的任务特征、已有代码和运行环境，不能自动 benchmark 所有 MATLAB toolbox 或 Python package。
- 文件与 source-tree digest 能证明身份一致，不能证明代码实现了预期数学公式。
- Targeted re-review 依赖正确的 P0 分类；reviewer 可能漏掉严重问题，也可能把普通 concern 误判为 P0。
- `plan_redo.py` 只能沿已记录的 ID 图推断影响。它看不到未被 `--source` 声明的隐式依赖（例如 run 读取了一个没有声明为 input 的文件），也无法判断一处数值变化在数学上是否真的改变结论。确定性检查仍然完整运行，以降低错误缩小范围的风险。
- 可见文本检查器按 `PREFIX-[Qn-]NNN` 的固定形状识别内部 ID，并识别常见本地 home 路径，但不能发现所有敏感字符串，也不能判断整体文风质量。
- Generic LaTeX scaffold 与具体年份提交格式无关。官方材料角色依赖 intake metadata：明确的 paper template 会优先采用/适配，规则说明只保留为合规输入；未正确分类的材料会保持 `unclassified`，最终仍需人工确认并逐页 QA。
- `paper_structure` 与通用间距能改善初始骨架，但不能预测真实长文中的 float 漂移、跨页表格、局部页面过空/过密或图中文字可读性；这些仍需下一次完整 CUMCM PDF 与质量参考进行人工逐页对比。
- 候选比较只能验证形式：恰好一个 selected、有理由、引用了真实运行。它无法判断你的 `discriminating_evidence` 是否真的能区分两个模型，也无法判断被淘汰的候选是不是其实更好——那是数学判断，属于独立复核。
- `acceptance_checks` 判为 `recorded` 的那些，现在是可机器判定的：求解程序必须自己写出同名断言，`CAP-E012` 核对它确实以 `source: "recorded"` 且 `passed: true` 出现在该能力的 official run 里。但**判据本身仍是人写的**——把"做到了"定义成一件太容易满足的事，机器照样放行。判为 `human` 的那些完全交给复核。
- 能力覆盖检查看的是"有没有模型认领、有没有在论文定稿时还没做完"。它看不出**清单本身漏列了题目要求的能力**——那取决于赛题分析阶段的理解力，是这条链最上游、也最不可机器化的一环。
- 冻结后的 `MODEL_CONTRACT` 可能退化成对已写好代码的事后描述。机器只能检查 `verification_plan` 是否对应到已记录的断言；"这是设计承诺还是代码转录"是 `REVIEW_REQUEST.md` 里点名的失败类，只能由 fresh-context reviewer 判断。
- `record_compile.py` 的 layout checks 来自编译日志，能发现 overfull box、未定义引用、缺字和字体错误，但发现不了"图中文字太小""这张表放错了位置"这类只有看图才知道的问题。逐页 PNG 已经渲染到 `.cumcm/tmp/pages/`，仍然需要人去看。
- claim 输出"是否由本次运行产生"靠执行前后的 mtime 判断。这挡得住"程序 exit 0 却没写文件"这类**疏漏**，挡不住有人先 `touch` 再跑——而在文件系统这一层，"被 touch 过的旧文件"和"确定性程序重写出的同样字节"本来就无法区分，任何本地检查都做不到。manifest 里记录了该输出运行前是否已存在（`preexisting`），供复核者事后判断；真正的边界仍然是：绕过 recorder 的行为，recorder 管不了。
- 冻结证据保证被保留的运行可验证，但它证明不了那次运行的数学是对的，也拦不住有人在冻结之前就把代码写错。
- `runs/` 会随重跑次数增长（每次一份源码和输出的副本）。CUMCM 规模下是几十 KB 量级；真正的大数据集作为 `formal_input` 不会被复制。
- 记录器只在被调用时记录。绕过 `record_run.py` 直接执行仍然可能产生无证据的结果；检查器只能发现"没有 official run 支撑"，不能发现"你在别处跑过"。

- 编译依赖来自 TeX recorder 的实际读取记录；首遍发现后至少一遍验证稳定输入。系统 TeX 树与字体仍是运行环境依赖，不装入源码 ZIP；`.bib` 等编译前生成工具的输入仍须声明为 `required_files`。这不是任意 TeX 宏或外部生成器的完整可复现环境封装。
- 返工计划会沿已声明的输出/正式输入依赖传递；对历史冻结输入采取保守提醒，需要先决定是否更新其绑定，不会自行替换历史方案或解决分叉。
