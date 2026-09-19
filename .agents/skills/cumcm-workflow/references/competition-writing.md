# Writing across competition languages and audiences

Use for English-language work, audience-specific deliverables, reference verification. Combine with [paper writing](06-paper-writing.md), which remains the common argument and QA guide. Check [competition adaptation](competition-adaptation.md) before choosing a generator: this guidance does not add an English template, a Word exporter or another contest's finalizing support to v0.6.

## Organize around the requested answer

Read the current official requirements for language, required sections, summary/cover sheets, supplementary letters or memoranda, anonymity, page accounting and output formats. Competition labels and previous papers do not establish any of these. An official requirement overrides a generic scaffold's default, including whether a table of contents is present.

Use the existing `PAPER_PLAN.paper_structure` and claim/representation selection for the mathematical argument. A Chinese engineering paper, an English modeling paper and a data-analysis report share the need to connect formulation, solution, result, evidence and limitations; they need not share heading order, length or typography. A diagram belongs when it explains a mechanism or dependency more clearly, not because a template demands one.

For a client-facing memo or recommendation, identify its audience and decision. Lead with the action, supporting result, tradeoff and conditions under which it should change. Map every quantitative statement back to the same reviewed claims as the technical paper. Do not add stronger causal, optimality or deployment claims for rhetorical impact. Include such a document only when requested or required, and verify its actual packaging separately from the paper.

## English summary and terminology

Write the summary after the body and results stabilize. Explain the problem, the decisive modeling idea, a few supported results with units or comparisons, and the important reliability boundary. If the organizer requires a separate Summary Sheet, check its exact current specification; do not manufacture a universal one-page or total-page limit.

Maintain consistent technical terms, notation, units and tense across sections. Preserve the strength of the evidence in translation: a feasible solution is not an optimal solution; a numerical check is not a proof; an association is not an effect. “Significant,” “robust,” “accurate” and “generalizable” need the corresponding evidence or a more precise description.

Use problem numbering when it helps navigation or is required, but do not force every paragraph to start with “For Problem N.” Independent questions may be presented separately; coupled questions should expose their shared mechanism and dependencies. Do not expand English prose to fill an estimated characters-per-page target.

## References and borrowed methods

For a reference actually used, verify bibliographic identity and that the inspected source supports the cited statement. Prefer the original method, dataset documentation or primary evidence. A valid DOI or search result proves neither that the source was read nor that it supports the claim. Keep uncertain references out of the final bibliography until checked; never invent a title, author, DOI or numerical benchmark.

Distinguish published benchmark values from results reproduced in this project. Cite external constants, datasets and borrowed equations where they enter the argument, preserving their units and applicability. Use only literature lookup allowed by the task and competition; missing organizer materials still follow the user-supplied-source boundary. There is no minimum citation count.

## Content review before cosmetic expansion

First repair task omissions, mathematical ambiguity, unsupported comparisons and contradictions between summary, tables and conclusions. Then improve explanations, captions and layout using existing evidence. Useful refinement answers a specific reader question; more pages, more charts or a mandatory “de-AI” rewrite does not establish quality.

Use the current quality report/revision log when a real finding needs tracking. Stop when consequential findings are resolved or transparently retained within scope, and further changes add little value under the available budget. A new experiment or changed conclusion follows the existing upstream revision and approval process. Recompile and inspect the changed artifact when source edits affect it; prior PDF review does not automatically cover the new PDF.

For Word or other formats, the scientific argument and evidence standards still apply, but inspect the actual exported equations, captions, tables, fonts and pagination. A good Markdown draft is not a verified DOCX or PDF, and it cannot satisfy v0.6's LaTeX receipt. Report that limitation rather than bypassing the checker.
