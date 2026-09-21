# Huawei Cup / graduate modeling contest delivery

Read this for 华为杯 / 中国研究生数学建模竞赛 (Huawei Cup, GMCM/CPGMCM/CPMCM). Reuse the existing stages, evidence and three human checkpoints. This guide supplies adaptation mechanics, not a permanent edition of organizer rules. The agent performs these commands; users supply the current official materials and review the final pages/files.

## Current materials and the historical template

Collect the current official template, format specification and submission instructions through the existing intake/source manifest. Record the competition/year and source locations of each interpreted requirement in `PROJECT_BRIEF.md`. Missing materials block final compliance, not unrelated exploratory modeling. Do not infer current requirements from a competition label.

The inspected reference asset used `gmcmthesis` v2.3 (2018) with a separate cover, abstract, and body. Reuse that separation and its distinction between cover identity and anonymous body. Do not inherit its bundled fonts, logos, institution fields, fixed section list, one-page abstract instruction, or catalog's 50-page target as current rules. No third-party class, font or logo is redistributed here.

Confirm from the supplied edition: cover/logos and allowed identity fields; abstract layout and limit; body typography; which pages must be anonymous; exact PDF filename; attachment names/formats/size limits; MD5 and upload order/deadlines. Record byte limits explicitly instead of silently choosing MB versus MiB. Do not hard-code a year, team-number length, paper-page quota, or assume that an example `.rar` name proves ZIP is forbidden/accepted.

## Cover and paper adaptation

Prefer the complete official LaTeX package when one exists; adapt it using the existing `official_package_adapter` manifest and retain the planned argument structure. For an official cover supplied in Word/PDF, fill the current official cover with real team information and export **only that cover** as a one-page PDF. Preserve its required logos and appearance. Register the original official template as `paper_template` in `SOURCE_MANIFEST`; the filled cover is a project-local derivative, not an invented official source.

For this cover-first route, after the existing validation checkpoint:

```bash
python3 "$S/init_latex_paper.py" --project <p> --competition '华为杯' \
  --competition-year <actual-year> --language zh \
  --title '<actual title>' --keywords '<actual methods>' \
  --cover-pdf paper-materials/filled-official-cover.pdf
```

The initializer requires a declared, existing official template and a one-page cover. It copies the cover into the editable source, includes it as the first PDF page and records `official_package_adapter`; `official_compliance` stays `unverified`. The remaining abstract/body are still the generic Chinese scaffold: adjust their typography and abstract layout against the current official template. This is not automatic DOCX conversion or proof of matching the organizer template. Preserve existing paper sources; initialization refuses overwrites.

Compile/render through `record_compile.py`, then inspect every page. The embedded cover joins the compile-bound source snapshot and editable package. Set compliance only after the current official requirements and rendered result have actually been reviewed. Check cover logos, field placement, page order, abstract styling, and identity in image-based text visually.

## Submission declarations and measured checks

Use the existing `delivery/DELIVERY_MANIFEST.json`. Add `submission.rules` after reading the current materials. The following is a **synthetic example**, not current official limits/names; replace every value with the actual project requirements:

```json
{
  "submission": {
    "rules": {
      "sources": ["problem/official/format.pdf", "problem/official/submission.pdf"],
      "pdf_name": "A123456.pdf",
      "cover_pages": 1,
      "identity_tokens": ["Actual University", "Actual Member", "123456"],
      "abstract": {
        "start_marker": "摘要",
        "body_marker": "1 问题重述",
        "max_pages": 2
      },
      "attachments": [
        {"path": "delivery/A123456.zip", "name": "A123456.zip",
         "max_bytes": 10000000, "formats": ["zip"]}
      ]
    }
  }
}
```

Include all known institution/team/member/student identifiers (including meaningful spelling variants) in `identity_tokens`. This declaration cannot establish that every identifier was listed. `sources` must reference local official format/submission/template materials classified in the source manifest; cite exact sections in the brief. `attachments` is empty only when no attachments are being submitted. The tool cannot infer missing required attachments from prose.

The abstract markers are unique visible headings in the actual PDF, not declared page counts. Use the full first body heading including its numbering; whitespace is normalized. The tool derives occupied abstract pages from their positions. Ambiguous/repeated markers, blank/image-only pages, or missing Poppler tools fail closed; adapt the extraction/markup and inspect the PDF rather than inventing a successful record. Running heads may require more specific markers. Text extraction is not OCR or visual compliance certification.

After final compilation, required submission naming, packaging and metadata refresh, run:

```bash
python3 "$S/submission_check.py" --project <p>          # inspect without writing
python3 "$S/submission_check.py" --project <p> --record # save measured checks
python3 "$S/cumcm_check.py" --project <p> --stage delivery --gate-mode preflight
```

`--record` writes only on success, into the existing manifest. The observed record includes actual PDF MD5/SHA256/size/page count, abstract span, rule-file hashes, rule-declaration hash, compile-receipt hash and attachment measurements. Never type these fields. `DELIVERY-E022` recomputes them: missing/inconsistent checks warn in working and block finalizing. Huawei-labeled projects require this check; other contests may opt in by declaring `submission`. Existing compile/source/approval checks remain in force.

The name in the final PDF declaration must match the name required for actual upload. Preserve the compile receipt's PDF and its source binding; if delivering a renamed copy, it must have identical bytes. Existing final-PDF binding checks still apply. Internal editable/computation ZIPs remain separate from organizer-facing attachments. The submission checker validates ZIP containers and recognizes RAR/7z signatures; it does not build RAR/7z, unpack those formats, inspect archive-member anonymity, or prove their contents are complete. Open and review the actual submission archive separately.

## Freeze, review, then submit the exact bytes

Create the submission record **before** the existing final human review, so the approval covers it and the exact rendered PDF. The record is a local byte-identity check, not an organizer upload receipt and not another human checkpoint. Submission remains user-controlled. Use the official platform/tool when the current rules require it.

When the current rules use MD5 -> PDF -> attachment stages, the MD5 must come from the exact PDF that will be uploaded. After sending MD5, do not recompile, edit metadata, optimize/compress, stamp, or otherwise regenerate the PDF. Re-run the read-only check before upload; a mismatch means stop, not silently issue a replacement MD5. Keep any platform acknowledgement separately as user-supplied evidence.

The recorder refuses to replace a different existing record, and `refresh_evidence.py` does not refresh it. Before submission, if a revision is deliberately authorized, use the existing revision/review procedure, explicitly remove the obsolete `submission.recorded` field, and re-record/review the new final artifact. After MD5 submission, do not erase the old record to bypass a mismatch: resolve the change through the current organizer process. Source hashes remain integrity evidence; MD5 exists solely for the contest submission protocol.
