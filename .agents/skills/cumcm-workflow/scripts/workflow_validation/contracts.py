"""Workflow contract names, paths, stages and schema versions."""

STAGES = [
    "intake",
    "problem-analysis",
    "model-design",
    "computation",
    "validation",
    "paper",
    "delivery",
]
STAGE_STATUSES = {
    "not_started",
    "in_progress",
    "passed",
    "needs_revision",
}
EVIDENCE_STATES = {
    "not_checked",
    "missing_evidence",
    "supported_not_reproduced",
    "reproduced",
    "partially_supported",
    "contradicted",
    "ambiguous",
    "not_applicable",
}
REVIEW_DECISIONS = {"unreviewed", "accepted", "accepted_with_concerns", "revision_requested"}
GATE_MODES = {"preflight", "enforce"}
WORKFLOW_VERSION = "0.8.0"
WORKFLOW_MODES = {"working", "finalizing"}


CONTRACT_PATHS = {
    "state": ".cumcm/state.json",
    "sources": "problem/SOURCE_MANIFEST.json",
    "facts": "analysis/PROBLEM_FACTS.json",
    "capabilities": "analysis/TASK_CAPABILITIES.json",
    "model": "model/MODEL_CONTRACT.json",
    "cross_question": "model/CROSS_QUESTION_LEDGER.json",
    "results": "results/RESULTS_INDEX.json",
    "independent_review_package": "validation/independent-review-package/REVIEW_PACKAGE_MANIFEST.json",
    "independent_review_result": "validation/INDEPENDENT_REVIEW_RESULT.json",
    "claims": "validation/CLAIM_LEDGER.json",
    "figures": "figures/FIGURE_MANIFEST.json",
    "paper_plan": "paper/PAPER_PLAN.json",
    "latex_template": "paper/LATEX_TEMPLATE_MANIFEST.json",
    "paper_quality": "paper/PAPER_QUALITY_REPORT.json",
    "paper_revisions": "paper/PAPER_REVISION_LOG.json",
    "paper_visible_text": "paper/PAPER_VISIBLE_TEXT_REPORT.json",
    "delivery": "delivery/DELIVERY_MANIFEST.json",
    "compile_receipt": "delivery/COMPILE_RECEIPT.json",
    "handoff_modeling_computation": "handoffs/modeling-computation/HANDOFF.json",
    "handoff_computation_validation": "handoffs/computation-validation/HANDOFF.json",
    "handoff_validation_paper": "handoffs/validation-paper/HANDOFF.json",
    "handoff_paper_delivery": "handoffs/paper-delivery/HANDOFF.json",
}

STAGE_CONTRACTS = {
    "intake": ("state", "sources"),
    "problem-analysis": ("state", "sources", "facts", "capabilities"),
    "model-design": ("state", "sources", "facts", "capabilities", "model"),
    "computation": ("state", "sources", "facts", "capabilities", "model", "results"),
    "validation": (
        "state", "sources", "facts", "capabilities", "model", "results",
        "independent_review_package", "independent_review_result", "claims",
    ),
    "paper": (
        "state", "sources", "facts", "capabilities", "model", "results",
        "independent_review_package", "independent_review_result", "claims",
        "paper_plan", "latex_template", "paper_quality", "paper_visible_text",
    ),
    "delivery": (
        "state", "sources", "facts", "capabilities", "model", "results",
        "independent_review_package", "independent_review_result", "claims",
        "paper_plan", "latex_template", "paper_quality", "paper_visible_text",
        "delivery", "compile_receipt",
    ),
}

# Contracts that only a frozen (finalizing) project must carry.
FINALIZING_CONTRACTS = {
    "model-design": ("cross_question",),
    "computation": ("cross_question",),
    "validation": ("cross_question",),
    "paper": ("cross_question",),
    "delivery": ("cross_question",),
}

# Contracts that are never required but are checked whenever the project has them,
# from the stage where they first make sense.
OPTIONAL_CONTRACTS = {
    "cross_question": "model-design",
    "figures": "validation",
    "paper_revisions": "paper",
}

PAPER_CONTRACTS = ("paper_plan", "latex_template", "paper_quality", "paper_visible_text")

SCHEMA_FILES = {
    "state": "workflow-state.schema.json",
    "sources": "source-manifest.schema.json",
    "facts": "problem-facts.schema.json",
    "capabilities": "task-capabilities.schema.json",
    "model": "model-contract.schema.json",
    "cross_question": "cross-question-ledger.schema.json",
    "results": "results-index.schema.json",
    "independent_review_package": "independent-review-package.schema.json",
    "independent_review_result": "independent-review-result.schema.json",
    "claims": "claim-ledger.schema.json",
    "figures": "figure-manifest.schema.json",
    "paper_plan": "paper-plan.schema.json",
    "latex_template": "latex-template-manifest.schema.json",
    "paper_quality": "paper-quality-report.schema.json",
    "paper_revisions": "paper-revision-log.schema.json",
    "paper_visible_text": "paper-visible-text-report.schema.json",
    "delivery": "delivery-manifest.schema.json",
    "compile_receipt": "compile-receipt.schema.json",
    "run": "run-manifest.schema.json",
    "handoff_modeling_computation": "handoff.schema.json",
    "handoff_computation_validation": "handoff.schema.json",
    "handoff_validation_paper": "handoff.schema.json",
    "handoff_paper_delivery": "handoff.schema.json",
}
