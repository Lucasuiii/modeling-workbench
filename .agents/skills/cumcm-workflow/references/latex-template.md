# Reader-facing LaTeX scaffold

For Huawei Cup / 中国研究生数学建模竞赛, also read [Huawei delivery adaptation](huawei-delivery.md): current official cover, abstract/anonymity checks, submission filenames, attachments and measured MD5 binding.

Initialize after a claim-led `PAPER_PLAN.json` exists:

```bash
python3 "$S/init_latex_paper.py" --project <project> --competition <actual-name> --language <zh-or-en> \
  --competition-year <year> \
  --title <title> --keywords '<actual object; model; method>'
```

`--competition` records the actual competition; it does not load a competition-specific format preset. `--language zh` uses the Chinese CTeX scaffold; `--language en` uses an English article scaffold with the same modular body and evidence binding. Omitted options retain CUMCM/Chinese defaults. The template mode `contest_article` identifies the English asset; it is not a new workflow mode. The existing Chinese asset ID `cumcm-contest-ctex` is retained for compatibility and does not override the manifest's actual competition name.

Supply `--title` and `--keywords` from the actual problem, model, data, or method. The initializer has no reader-facing generic fallback and rejects generic title placeholders or workflow-oriented keyword filler.

The initializer checks exact subproblem coverage through `paper_structure`, stages all generated files, and publishes them transactionally with rollback if a commit fails. It refuses to overwrite existing source. If source metadata declares an adaptable official paper template, generic initialization stops so that template can be adopted or adapted. Format/submission/competition instructions do not block generic initialization; they remain bound official materials and `official_compliance` stays `unverified` until paper/delivery checks them. Filename keywords alone do not decide the role.

The scaffold keeps setup in `main.tex`, metadata in `metadata.tex`, shared notation/macros in `macros.tex`, and substantive writing in `sections/`. Abstract, references, and appendix are generic outer modules. Every body section and its input order come directly from `PAPER_PLAN.paper_structure`; the initializer does not generate per-question subsection trees or a LaTeX AST. Purpose, covered-subproblem IDs, and claim IDs appear only as comments for the writer and never render.

Remove placeholder markers before final status. Add only figures/tables selected for a real claim. Keep internal IDs out of rendered text; `paper_visible_text_check.py` measures that on the PDF. The generic scaffold is submission-neutral; adapt a user-supplied official package when required.

## Typography the scaffold already settles

Table captions sit above the table, figure captions below. Tables are three-line (`booktabs`): `\toprule`, one `\midrule` under the header, `\bottomrule`, and no vertical rules. A symbol table with more than a handful of entries is grouped by module rather than listed flat — `\symgroup{几何光学}` opens a block, and the reader finds a symbol by knowing which part of the model it belongs to:

```latex
\begin{tabular}{lll}
\toprule 符号 & 含义 & 单位 \\
\symgroup{几何光学}
$d$ & 外延层厚度 & \si{\micro\metre} \\
\symgroup{色散模型}
$\varepsilon_\infty$ & 高频介电常数 & 1 \\
\bottomrule
\end{tabular}
```

Units are typed in math mode (`$7.413\,\mathrm{\mu m}$`, `$970\,\mathrm{cm}^{-1}$`) rather than through a units package, so the scaffold compiles on a minimal TeX install; keep the spacing and the roman unit consistent across the paper. `\keyresult{}` bolds a value that is itself an answer; see `references/06-paper-writing.md` for when to use it.

TikZ (`texlive-pictures` on a Debian-family TeX install) is loaded with `arrows.meta`, `positioning`, `calc`, `shapes.geometric`, `fit` and `backgrounds`. This is a capability, not an instruction: mechanism sketches, decision flows and state diagrams carry no data and so are easy to overlook, and the packages are present so that drawing one is cheap when a claim needs it. Whether any figure belongs is decided per claim in `representation_plan`. The scaffold ships no figure and no figure placeholder.

For plotted figures, `assets/plot-style/cumcm.mplstyle` fixes sizes, fonts, grid and colours so every plot in the paper reads as one system. Point matplotlib at it and set a CJK family that exists on the machine; the file's header shows both lines. It does not decide what to plot either.

The generic style uses restrained heading/equation/float spacing, booktabs-friendly tables, `tabularx`/`longtable`, and subfigure support. Do not shrink dense tables reflexively or force floats away from their argument. Compile with `record_compile.py`. It runs the declared engine, writes `COMPILE_RECEIPT.json` with the PDF hash and a `sha256-tree-v1` snapshot of every required source file, reads the page count out of the PDF, rasterises every page to `.cumcm/tmp/pages/`, and derives the layout checks (overfull boxes, undefined references, missing glyphs, font errors) from the engine log:

```bash
python3 "$S/record_compile.py" --project <p> --update-quality
```

With `--update-quality` it refreshes the machine fields of `PAPER_QUALITY_REPORT.layout_report` — page count, rendered pages, checks, bound artifact. The report carries no decision of its own; the single approval before submission is `DELIVERY_MANIFEST.final_check`, and the pages rendered here are what it must present. Then actually look at the rendered pages: equations, tables, captions, figure placement, page density, whitespace, fonts and cross-page continuity are human QA, not a machine score.

The initializer records each planned `section_id` and its generated TeX path in `LATEX_TEMPLATE_MANIFEST.section_paths`, including sections with no subproblem IDs. Preserve this mapping when adapting or moving sections. Redo planning uses it for claim dependencies; an unmapped claim-only section conservatively invalidates all declared sections.
