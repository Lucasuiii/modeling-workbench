"""Guards for the two entry points and for the vocabulary v0.6 removed."""

from __future__ import annotations

import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CANONICAL = ROOT / ".agents" / "skills" / "cumcm-workflow"
CLAUDE_SKILL = ROOT / ".claude" / "skills" / "cumcm-workflow" / "SKILL.md"
SCRIPTS = CANONICAL / "scripts"

REMOVED_VOCABULARY = (
    "PAPER_TRACEABILITY",
    "paper-traceability",
    "conclusions_withheld",
    "plan_scoped_revalidation",
    "--profile",
    "awaiting_review\"",
)


def frontmatter(path: Path) -> dict[str, str]:
    text = path.read_text(encoding="utf-8")
    match = re.match(r"^---\n(.*?)\n---\n", text, re.S)
    assert match, f"{path} has no YAML frontmatter"
    fields = {}
    for line in match.group(1).splitlines():
        key, _, value = line.partition(":")
        if value.strip():
            fields[key.strip()] = value.strip()
    return fields


class EntryPointTests(unittest.TestCase):
    def test_both_entry_points_declare_the_same_skill(self):
        codex = frontmatter(CANONICAL / "SKILL.md")
        claude = frontmatter(CLAUDE_SKILL)
        self.assertEqual(codex["name"], "cumcm-workflow")
        self.assertEqual(claude["name"], "cumcm-workflow")
        for field in ("name", "description"):
            self.assertIn(field, claude, "Claude Code requires name and description in the frontmatter")
        self.assertGreater(len(claude["description"]), 40)

    def test_claude_router_link_resolves_from_its_own_directory(self):
        text = CLAUDE_SKILL.read_text(encoding="utf-8")
        links = re.findall(r"\]\(([^)]+)\)", text)
        self.assertEqual(len(links), 1)
        self.assertEqual((CLAUDE_SKILL.parent / links[0]).resolve(), CANONICAL / "SKILL.md")
        self.assertEqual(frontmatter(CLAUDE_SKILL), frontmatter(CANONICAL / "SKILL.md"))

    def test_complete_personal_skill_can_run_from_an_unrelated_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            installed = root / 'personal skills/cumcm-workflow'
            shutil.copytree(CANONICAL, installed, ignore=shutil.ignore_patterns('__pycache__'))
            workspace = root / 'contest'; workspace.mkdir()
            done = subprocess.run([sys.executable, str(installed / 'scripts/init_project.py'), '--help'],
                                  cwd=workspace, capture_output=True, text=True)
            self.assertEqual(done.returncode, 0, done.stderr)
            for name in ('references', 'schemas', 'assets'):
                self.assertTrue((installed / name).is_dir())
            linked = root / 'linked-skill'
            linked.symlink_to(CANONICAL, target_is_directory=True)
            self.assertEqual((linked / 'SKILL.md').resolve(), CANONICAL / 'SKILL.md')

    def test_both_repo_editing_entry_points_lead_to_one_rule_set(self):
        """The repository is maintained from Codex and from Claude Code.

        CLAUDE.md holds the invariants; AGENTS.md is what Codex looks for. It routes and
        restates nothing, the same shape as the Claude Code skill router, so a rule cannot
        end up stated in one place and contradicted in the other.
        """
        agents = ROOT / "AGENTS.md"
        self.assertTrue(agents.is_file(), "Codex has no repository-editing entry point")
        text = agents.read_text(encoding="utf-8")
        self.assertIn("CLAUDE.md", text)
        self.assertIn(".agents/skills/cumcm-workflow/SKILL.md", text)
        self.assertLess(len(text.encode("utf-8")), 2048, "AGENTS.md is long enough to be a second rule set")
        claude_md = (ROOT / "CLAUDE.md").read_text(encoding="utf-8")
        for invariant in ("Machine facts are recorded", "Declared is not recorded", "Two knobs only"):
            with self.subTest(invariant=invariant):
                self.assertIn(invariant, claude_md)
                self.assertNotIn(invariant, text)

    def test_codex_manifest_still_present(self):
        manifest = CANONICAL / "agents" / "openai.yaml"
        self.assertTrue(manifest.is_file(), "the Codex entry point must survive the Claude Code addition")
        self.assertIn("cumcm-workflow", manifest.read_text(encoding="utf-8"))

    def test_every_referenced_reference_file_exists(self):
        text = (CANONICAL / "SKILL.md").read_text(encoding="utf-8")
        for name in sorted(set(re.findall(r"\(references/([a-z0-9-]+\.md)\)", text))):
            with self.subTest(reference=name):
                self.assertTrue((CANONICAL / "references" / name).is_file())

    def test_scripts_named_in_the_canonical_skill_exist(self):
        text = (CANONICAL / "SKILL.md").read_text(encoding="utf-8")
        for name in sorted(set(re.findall(r"scripts/([a-z_0-9]+\.py)", text))):
            with self.subTest(script=name):
                self.assertTrue((SCRIPTS / name).is_file())


class ContinuousIntegrationTests(unittest.TestCase):
    """A test pattern that matches nothing exits 5 and reads as a green-ish failure.

    This is exactly what happened when the v0.6 test files were renamed after the
    workflow was written, so the patterns are checked against the tree.
    """

    def workflow_text(self) -> str:
        return (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")

    def test_every_ci_discover_pattern_matches_at_least_one_test_file(self):
        patterns = re.findall(r"unittest discover -s (\S+) -p '([^']+)'", self.workflow_text())
        self.assertTrue(patterns, "no unittest discover invocation found in the CI workflow")
        for directory, pattern in patterns:
            with self.subTest(pattern=pattern):
                matched = sorted((ROOT / directory).glob(pattern))
                self.assertTrue(matched, f"CI pattern {pattern!r} in {directory} matches no file")

    def test_ci_installs_what_the_compile_tests_need(self):
        text = self.workflow_text()
        for package in ("texlive-xetex", "texlive-lang-chinese", "poppler-utils"):
            with self.subTest(package=package):
                self.assertIn(package, text)


class RemovedVocabularyTests(unittest.TestCase):
    """Instruction files must not tell an agent to produce something v0.6 deleted.

    Design and migration documents are exempt on purpose: explaining what was
    removed is exactly their job.
    """

    def instruction_files(self) -> list[Path]:
        paths = [CANONICAL / "SKILL.md", CLAUDE_SKILL, ROOT / "CLAUDE.md"]
        paths += sorted((CANONICAL / "assets").rglob("*.md"))
        return paths

    def test_instruction_files_do_not_promise_removed_features(self):
        for path in self.instruction_files():
            text = path.read_text(encoding="utf-8")
            for token in REMOVED_VOCABULARY:
                with self.subTest(document=path.name, token=token):
                    self.assertNotIn(token, text)

    def test_readmes_do_not_document_the_deleted_profile_flag(self):
        for name in ("README.md", "README.en.md"):
            text = (ROOT / name).read_text(encoding="utf-8")
            with self.subTest(document=name):
                self.assertNotIn("--profile", text)

    def test_scripts_and_schemas_do_not_mention_removed_contracts(self):
        for path in sorted(SCRIPTS.rglob("*.py")) + sorted((CANONICAL / "schemas").glob("*.json")):
            text = path.read_text(encoding="utf-8")
            for token in ("PAPER_TRACEABILITY", "conclusions_withheld", "PROFILES"):
                with self.subTest(path=path.name, token=token):
                    self.assertNotIn(token, text)


if __name__ == "__main__":
    unittest.main()
