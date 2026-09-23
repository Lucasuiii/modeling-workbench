# 文档导航

1. [v0.6 设计](v0.6-design.md)：为什么把投入从"检查声称"搬到"自动取证"，以及候选模型如何靠证据选出。
2. [架构](architecture.md)：orchestrator、fresh task、handoff、snapshot 与两个运行模式。
3. [工作流合同](workflow-contract.md)：各职责的 hard invariant、warning 和 gate 语义。
4. [项目 provenance](provenance.md)：哪些对象需要 digest，以及 digest 不能证明什么。
5. [已知限制](limitations.md)：reviewer 独立性、后端选择、语义检查，以及 Windows/WSL2 与 CI 的验证边界。

实际使用从仓库根目录的 [README](../README.md) 开始；机器可执行规则以 `.agents/skills/cumcm-workflow/` 中的 Skill、schema 和 script 为准。

v0.6 不向下兼容，仓库不保留历史版本设计文档与迁移脚本。
