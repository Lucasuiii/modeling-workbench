#!/usr/bin/env python3
"""Initialize a modular v0.6 contest LaTeX paper without overwriting existing work."""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from official_materials import classified_official_materials


WORKFLOW_VERSION = "0.6.0"
TEMPLATE_DIRS = {"zh": "generic-ctex", "en": "generic-en"}


def read_object(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot read {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"expected a JSON object: {path}")
    return value


def latex_escape(value: str) -> str:
    replacements = {
        "\\": r"\textbackslash{}",
        "&": r"\&",
        "%": r"\%",
        "$": r"\$",
        "#": r"\#",
        "_": r"\_",
        "{": r"\{",
        "}": r"\}",
        "~": r"\textasciitilde{}",
        "^": r"\textasciicircum{}",
    }
    return "".join(replacements.get(char, char) for char in value)


def safe_slug(value: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9]+", "_", value).strip("_").lower()
    return slug or "section"


def comment_text(value: Any) -> str:
    """Keep paper-plan metadata readable but inert inside LaTeX comments."""
    return " ".join(str(value).replace("%", "％").split())


def validate_keywords(keywords: str) -> str:
    value = keywords.strip()
    if not value:
        raise ValueError("provide --keywords from the actual problem, model, or method")
    folded = value.casefold()
    banned = ("数学建模", "可复现计算", "证据链", "reproducible computation", "evidence chain")
    if any(term in folded for term in banned):
        raise ValueError("keywords must name the actual problem, model, data, or method, not workflow concepts")
    return value


def validate_title(title: str) -> str:
    value = title.strip()
    placeholders = {
        "全国大学生数学建模竞赛论文",
        "cumcm paper",
        "paper title",
        "论文标题",
        "标题待定",
    }
    if not value or value.casefold() in {item.casefold() for item in placeholders}:
        raise ValueError("provide --title from the actual problem; generic title placeholders may not enter reader-facing output")
    return value


def official_paper_template_sources(project: Path) -> list[str]:
    manifest_path = project / "problem" / "SOURCE_MANIFEST.json"
    if not manifest_path.is_file():
        return []
    manifest = read_object(manifest_path)
    return [
        str(item.get("path"))
        for item in classified_official_materials(manifest.get("sources", []))
        if item.get("role") == "paper_template"
    ]


def render(template: str, values: dict[str, str]) -> str:
    result = template
    for key, value in values.items():
        result = result.replace(f"@@{key}@@", value)
    unresolved = sorted(set(re.findall(r"@@[A-Z0-9_]+@@", result)))
    if unresolved:
        raise ValueError(f"unresolved template tokens: {', '.join(unresolved)}")
    return result


def validate_inputs(project: Path) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    state = read_object(project / ".cumcm" / "state.json")
    facts = read_object(project / "analysis" / "PROBLEM_FACTS.json")
    plan = read_object(project / "paper" / "PAPER_PLAN.json")
    if state.get("workflow_version") != WORKFLOW_VERSION or state.get("schema_version") != WORKFLOW_VERSION:
        raise ValueError("LaTeX initialization requires an exact v0.6 workflow state")
    project_ids = {state.get("project_id"), facts.get("project_id"), plan.get("project_id")}
    if None in project_ids or len(project_ids) != 1:
        raise ValueError("state, problem facts, and paper plan must share one project_id")
    subproblems = facts.get("subproblems")
    if not isinstance(subproblems, list) or not subproblems:
        raise ValueError("PROBLEM_FACTS.json must contain at least one subproblem")
    fact_ids = {
        str(item.get("subproblem_id") or item.get("id"))
        for item in subproblems
        if isinstance(item, dict) and (item.get("subproblem_id") or item.get("id"))
    }
    structure = plan.get("paper_structure")
    if not isinstance(structure, list) or not structure:
        raise ValueError("PAPER_PLAN.json must contain a non-empty paper_structure")
    for index, item in enumerate(structure, 1):
        if not isinstance(item, dict):
            raise ValueError(f"paper_structure item {index} must be an object")
        if not all(comment_text(item.get(field, "")) for field in ("section_id", "title", "purpose")):
            raise ValueError(f"paper_structure item {index} requires section_id, title, and purpose")
        if not isinstance(item.get("subproblem_ids"), list) or not isinstance(item.get("claim_ids"), list):
            raise ValueError(f"paper_structure item {index} requires subproblem_ids and claim_ids arrays")
    plan_ids = {
        str(subproblem_id)
        for item in structure
        if isinstance(item, dict)
        for subproblem_id in item.get("subproblem_ids", [])
        if str(subproblem_id)
    }
    if fact_ids != plan_ids:
        raise ValueError("paper structure must exactly cover the problem-fact subproblems")
    return state, facts, plan


def commit_staged_tree(staging: Path, paper_dir: Path) -> None:
    """Publish generated top-level entries with rollback on a partial commit."""
    sources = sorted(staging.iterdir(), key=lambda path: path.name)
    conflicts = [paper_dir / source.name for source in sources if (paper_dir / source.name).exists()]
    if conflicts:
        raise ValueError("refusing to overwrite paper files during commit: " + ", ".join(path.name for path in conflicts))
    paper_dir.mkdir(parents=True, exist_ok=True)
    created: list[Path] = []
    try:
        for source in sources:
            destination = paper_dir / source.name
            os.replace(source, destination)
            created.append(destination)
    except OSError:
        for destination in reversed(created):
            if destination.is_dir():
                shutil.rmtree(destination)
            elif destination.exists():
                destination.unlink()
        raise


def initialize(
    project: Path, title: str, competition_year: int, keywords: str,
    *, competition: str = "CUMCM", language: str = "zh", cover_pdf: str | None = None,
) -> Path:
    competition = competition.strip()
    if not competition or any(ord(char) < 32 for char in competition):
        raise ValueError("competition must be a non-empty name without control characters")
    if language not in TEMPLATE_DIRS:
        raise ValueError("language must be zh or en")
    state, _, plan = validate_inputs(project)
    from workflow_checks import require_human_checkpoint
    require_human_checkpoint(project, "validation")
    skill_root = Path(__file__).resolve().parents[1]
    template_root = skill_root / "assets" / "latex-template" / TEMPLATE_DIRS[language]
    template_meta = read_object(template_root / "template.json")
    template_sources = official_paper_template_sources(project)
    cover = None
    if cover_pdf is not None:
        cover = (project / cover_pdf).resolve()
        if not cover.is_relative_to(project.resolve()) or not cover.is_file() or cover.suffix.lower() != ".pdf":
            raise ValueError("cover PDF must be an existing project-local PDF")
        if language != "zh" or not template_sources:
            raise ValueError("cover adaptation requires Chinese output and a declared official paper template")
        for source in template_sources:
            target = (project / source).resolve()
            if not target.is_relative_to(project.resolve()) or not target.is_file():
                raise ValueError("declared official template must exist inside the project")
        try:
            info = subprocess.run(["pdfinfo", str(cover)], capture_output=True, text=True, check=True, timeout=30)
        except (OSError, subprocess.SubprocessError) as exc:
            raise ValueError(f"cannot inspect cover PDF: {exc}") from exc
        if not re.search(r"^Pages:\s+1\s*$", info.stdout, re.MULTILINE):
            raise ValueError("cover PDF must contain exactly one page")
    if template_sources and cover is None:
        raise ValueError(
            "an official paper template is declared; adopt or adapt it before using the generic scaffold: "
            + ", ".join(template_sources)
        )
    paper_dir = project / "paper"
    protected_targets = [paper_dir / "main.tex", paper_dir / "metadata.tex", paper_dir / "macros.tex", paper_dir / "references.bib", paper_dir / "sections", paper_dir / "LATEX_TEMPLATE_MANIFEST.json"]
    if cover is not None:
        protected_targets.append(paper_dir / "official-cover.pdf")
    conflicts = [path for path in protected_targets if path.exists()]
    if conflicts:
        listed = ", ".join(path.relative_to(project).as_posix() for path in conflicts)
        raise ValueError(f"refusing to overwrite existing paper sources: {listed}")

    structure = [item for item in plan["paper_structure"] if isinstance(item, dict)]
    subproblem_records: list[dict[str, str]] = []
    section_paths: list[dict[str, str]] = []
    section_inputs: list[str] = []
    chosen_title = validate_title(title)
    chosen_keywords = validate_keywords(keywords)
    generated_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    temp_parent = project / ".cumcm" / "tmp"
    temp_parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="latex-init-", dir=temp_parent) as temp:
        staging = Path(temp) / "paper"
        sections = staging / "sections"
        sections.mkdir(parents=True)
        for name in ("00_abstract.tex", "98_references.tex", "99_appendix.tex"):
            shutil.copy2(template_root / "sections" / name, sections / name)
        shutil.copy2(template_root / "macros.tex", staging / "macros.tex")
        shutil.copy2(template_root / "references.bib", staging / "references.bib")

        section_template = (template_root / "planned-section.tex.tmpl").read_text(encoding="utf-8")
        for index, item in enumerate(structure, 1):
            section_id = str(item.get("section_id", ""))
            title_value = comment_text(item.get("title", ""))
            purpose = comment_text(item.get("purpose", ""))
            subproblem_ids = [str(value) for value in item.get("subproblem_ids", [])]
            claim_ids = [str(value) for value in item.get("claim_ids", [])]
            filename = f"{index * 10:02d}_{safe_slug(section_id or title_value)}.tex"
            rel = f"paper/sections/{filename}"
            content = render(
                section_template,
                {
                    "SECTION_TITLE": latex_escape(title_value),
                    "SECTION_ID": comment_text(section_id),
                    "SECTION_PURPOSE": comment_text(purpose),
                    "SUBPROBLEM_IDS": comment_text(", ".join(subproblem_ids) or "none"),
                    "CLAIM_IDS": comment_text(", ".join(claim_ids) or "none"),
                },
            )
            (sections / filename).write_text(content, encoding="utf-8")
            section_paths.append({"section_id": section_id, "path": rel})
            for subproblem_id in subproblem_ids:
                subproblem_records.append({"subproblem_id": subproblem_id, "path": rel})
            section_inputs.append(f"\\input{{sections/{filename[:-4]}}}")

        main_text = render(
            (template_root / "main.tex.tmpl").read_text(encoding="utf-8"),
            {"PLANNED_SECTION_INPUTS": "\n".join(section_inputs)},
        )
        if cover is not None:
            shutil.copy2(cover, staging / "official-cover.pdf")
            main_text = main_text.replace(r"\begin{document}",
                "\\usepackage{pdfpages}\n\\begin{document}\n"
                "\\includepdf[pages=1,pagecommand={}]{official-cover.pdf}\n"
                "\\setcounter{page}{1}")
        metadata_text = render(
            (template_root / "metadata.tex.tmpl").read_text(encoding="utf-8"),
            {
                "PROJECT_ID": str(state["project_id"]),
                "TITLE": latex_escape(chosen_title),
                "COMPETITION_YEAR": str(competition_year),
                "KEYWORDS": latex_escape(chosen_keywords),
            },
        )
        (staging / "main.tex").write_text(main_text, encoding="utf-8")
        (staging / "metadata.tex").write_text(metadata_text, encoding="utf-8")

        section_files = sorted(f"paper/sections/{path.name}" for path in sections.glob("*.tex"))
        required_files = ["paper/main.tex", "paper/metadata.tex", "paper/macros.tex", "paper/references.bib", *section_files]
        if cover is not None:
            required_files.append("paper/official-cover.pdf")
        manifest = {
            "schema_version": WORKFLOW_VERSION,
            "artifact_type": "latex_template_manifest",
            "project_id": state["project_id"],
            "updated_at": generated_at,
            "producer": {"kind": "script", "name": "init_latex_paper.py", "version": WORKFLOW_VERSION},
            "template_id": template_meta["template_id"],
            "template_version": template_meta["template_version"],
            "mode": "official_package_adapter" if cover is not None else template_meta["mode"],
            "engine": template_meta["engine"],
            "competition": competition,
            "competition_year": competition_year,
            "official_compliance": "unverified",
            "official_template_source": template_sources[0] if cover is not None else None,
            "main_path": "paper/main.tex",
            "metadata_path": "paper/metadata.tex",
            "section_files": section_files,
            "subproblem_sections": subproblem_records,
            "section_paths": section_paths,
            "required_files": required_files,
            "placeholder_markers": ["CUMCM-TODO", "\\placeholder{"],
            "template_source": f"repo_asset:{template_meta['template_id']}@{template_meta['template_version']}",
        }
        (staging / "LATEX_TEMPLATE_MANIFEST.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

        commit_staged_tree(staging, paper_dir)

    return paper_dir / "LATEX_TEMPLATE_MANIFEST.json"


def main() -> int:
    parser = argparse.ArgumentParser(description="Initialize a Chinese or English contest LaTeX scaffold for a v0.6 project")
    parser.add_argument("--project", required=True, type=Path)
    parser.add_argument("--title", required=True, help="reader-facing title derived from the actual problem")
    parser.add_argument("--competition-year", type=int, default=datetime.now().year)
    parser.add_argument("--competition", default="CUMCM", help="actual competition name from supplied materials; not a rules preset")
    parser.add_argument("--language", choices=sorted(TEMPLATE_DIRS), default="zh", help="paper scaffold language; independent of competition name")
    parser.add_argument("--keywords", required=True, help="semicolon-separated keywords from the actual problem, model, or method")
    parser.add_argument("--cover-pdf", help="project-local one-page cover filled from the declared official template; remaining format needs review")
    args = parser.parse_args()
    project = args.project.resolve()
    if not project.is_dir():
        parser.error(f"project is not a directory: {project}")
    try:
        manifest = initialize(project, args.title, args.competition_year, args.keywords,
                              competition=args.competition, language=args.language, cover_pdf=args.cover_pdf)
    except ValueError as exc:
        parser.error(str(exc))
    print(f"initialized modular LaTeX paper: {manifest}")
    print("official format compliance remains unverified until checked against the current competition package and rules")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
