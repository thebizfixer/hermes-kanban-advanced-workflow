"""Tests for evaluation chain prior-commit and verification paths."""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "scripts" / "lib"))

from card_body import find_prior_commit, is_verification_only, parse_card_body  # noqa: E402
import kanban_evaluation_chain as chain  # noqa: E402


def _git(cwd: str, *args: str) -> None:
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True)


class TestEvaluationChain(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = self.tmp.name
        _git(self.repo, "init")
        _git(self.repo, "config", "user.email", "t@example.com")
        _git(self.repo, "config", "user.name", "Test")
        path = os.path.join(self.repo, "src", "foo.py")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write("v1\n")
        _git(self.repo, "add", ".")
        _git(self.repo, "commit", "-m", "baseline")

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_find_prior_commit_message_and_files(self) -> None:
        path = os.path.join(self.repo, "src", "foo.py")
        with open(path, "w", encoding="utf-8") as f:
            f.write("v2\n")
        _git(self.repo, "add", "src/foo.py")
        _git(self.repo, "commit", "-m", "feat: add foo handler")

        with open(path, "w", encoding="utf-8") as f:
            f.write("v3\n")
        _git(self.repo, "add", "src/foo.py")
        _git(self.repo, "commit", "-m", "chore: noop")

        sha = find_prior_commit(
            "feat: add foo handler",
            ["src/foo.py"],
            self.repo,
            "HEAD~1",
        )
        self.assertIsNotNone(sha)

    def test_find_prior_commit_lookback_beyond_baseline(self) -> None:
        path = os.path.join(self.repo, "src", "foo.py")
        with open(path, "w", encoding="utf-8") as f:
            f.write("v2\n")
        _git(self.repo, "add", "src/foo.py")
        _git(self.repo, "commit", "-m", "feat: layer0 url dedup")

        for i in range(4):
            _git(self.repo, "commit", "--allow-empty", "-m", f"chore: filler {i}")

        sha = find_prior_commit(
            "feat: layer0 url dedup",
            ["src/foo.py"],
            self.repo,
            "HEAD~1",
        )
        self.assertIsNotNone(sha)

    def test_find_prior_commit_denies_message_only(self) -> None:
        path = os.path.join(self.repo, "src", "bar.py")
        with open(path, "w", encoding="utf-8") as f:
            f.write("x\n")
        _git(self.repo, "add", "src/bar.py")
        _git(self.repo, "commit", "-m", "feat: add foo handler")

        sha = find_prior_commit(
            "feat: add foo handler",
            ["src/foo.py"],
            self.repo,
            "HEAD~1",
        )
        self.assertIsNone(sha)

    def test_parse_decompose_yaml_frontmatter(self) -> None:
        body = """plan_id: plan-x
files:
  - src/foo.py
mode: modify-only
tests: pytest tests/test_foo.py
commit: "feat: add foo"
"""
        parsed = parse_card_body(body)
        self.assertEqual(parsed["files"], ["src/foo.py"])
        self.assertEqual(parsed["tests"], "pytest tests/test_foo.py")
        self.assertEqual(parsed["commit"], "feat: add foo")

    def test_verification_only_classification(self) -> None:
        body = """Type: verification
Tests: pytest tests/test_x.py
Commit: N/A (verification only)
Mode: read-only
"""
        parsed = parse_card_body(body)
        self.assertTrue(is_verification_only(parsed, body))

    def test_step_1_already_committed_allow(self) -> None:
        path = os.path.join(self.repo, "src", "foo.py")
        with open(path, "w", encoding="utf-8") as f:
            f.write("v2\n")
        _git(self.repo, "add", "src/foo.py")
        _git(self.repo, "commit", "-m", "feat: card work")

        _git(self.repo, "commit", "--allow-empty", "-m", "empty follow-up")

        ok, err = chain.step_1_file_compliance(
            ["src/foo.py"],
            "HEAD~1",
            self.repo,
            "feat: card work",
        )
        self.assertTrue(ok)
        self.assertIsNone(err)

    def test_verification_chain_path(self) -> None:
        body = """Type: verification
Tests:
Commit: N/A (verification only)
Mode: read-only
"""
        passed, reason = chain.run_chain(
            "t_test1234",
            self.repo,
            body,
            baseline="HEAD~1",
            token_log="",
            lattice_memory_path="",
            registry_path="",
        )
        self.assertFalse(passed)
        self.assertIn("verification_only", reason)

    def test_verification_deploy_blocks_without_attestation(self) -> None:
        body = """plan_id: plan-x
card_key: deploy-smoke
Type: verification-deploy
Tests: echo ok
Deploy: operator browser smoke
Mode: read-only
"""
        passed, reason = chain.run_chain(
            "t_deploy01",
            self.repo,
            body,
            baseline="HEAD~1",
            token_log="",
            lattice_memory_path="",
            registry_path="",
        )
        self.assertFalse(passed)
        self.assertIn("attestation", reason.lower())

    def test_presentation_acceptance_skips_without_markers(self) -> None:
        ok, err = chain.step_presentation_acceptance("Files: a.py\nMode: modify-only\n", self.repo)
        self.assertTrue(ok)
        self.assertIsNone(err)

    def test_pre_existing_allows_merge_base_diff(self) -> None:
        path = os.path.join(self.repo, "src", "foo.py")
        with open(path, "w", encoding="utf-8") as f:
            f.write("v2\n")
        _git(self.repo, "add", "src/foo.py")
        _git(self.repo, "commit", "-m", "feat: pre-work")

        body = "plan_id: p1\npre_existing: true\nfiles:\n  - src/foo.py\n"
        ok, err = chain.step_1_file_compliance(
            ["src/foo.py"],
            "HEAD~1",
            self.repo,
            card_body=body,
            working_branch="main",
        )
        self.assertTrue(ok, err)
        self.assertIsNone(err)

    def test_diff_range_env_override(self) -> None:
        prev = os.environ.get("KANBAN_EVAL_BASELINE")
        try:
            os.environ["KANBAN_EVAL_BASELINE"] = "HEAD~2"
            self.assertEqual(chain._diff_range("HEAD~1", self.repo), "HEAD~2..HEAD")
        finally:
            if prev is None:
                os.environ.pop("KANBAN_EVAL_BASELINE", None)
            else:
                os.environ["KANBAN_EVAL_BASELINE"] = prev

    # ── E021: Acceptance test coverage ──

    def test_acceptance_test_coverage_allows_when_test_in_diff(self) -> None:
        """Card Acceptance names a test file that exists in git diff → ALLOW."""
        # Create a test file and commit it
        test_path = os.path.join(self.repo, "tests", "test_new_feature.py")
        os.makedirs(os.path.dirname(test_path), exist_ok=True)
        with open(test_path, "w", encoding="utf-8") as f:
            f.write("def test_feature(): pass\n")
        _git(self.repo, "add", "tests/test_new_feature.py")
        _git(self.repo, "commit", "-m", "feat: add new feature")

        card_body = """Type: code
Files: src/foo.py
Tests: pytest tests/
Acceptance:
- 1. rg 'def test_feature' tests/test_new_feature.py — assert test exists
- 2. tests/test_new_feature.py has def test_feature"""
        ok, err = chain.step_acceptance_test_coverage(
            card_body, "HEAD~1", self.repo
        )
        self.assertTrue(ok, err)
        self.assertIsNone(err)

    def test_acceptance_test_coverage_denies_missing_test(self) -> None:
        """Card Acceptance names a test file not in the diff → DENY."""
        card_body = """Type: code
Files: src/foo.py
Tests: pytest tests/
Acceptance:
- 1. rg 'def test_missing' tests/test_missing.py — new test file
- 2. tests/test_missing.py must exist"""
        ok, err = chain.step_acceptance_test_coverage(
            card_body, "HEAD~1", self.repo
        )
        self.assertFalse(ok)
        self.assertEqual(err, "E021_ACCEPTANCE_TEST_MISSING")

    def test_acceptance_test_coverage_no_refs_is_noop(self) -> None:
        """Card without Acceptance test refs → ALLOW (no-op)."""
        card_body = """Type: code
Files: src/foo.py
Tests: pytest
Commit: feat: no tests mentioned"""
        ok, err = chain.step_acceptance_test_coverage(
            card_body, "HEAD~1", self.repo
        )
        self.assertTrue(ok)
        self.assertIsNone(err)

    # ── E022: Docs HEAD verify ──

    def test_docs_head_verify_allows_clean_verify(self) -> None:
        """Docs card Verify: rg matches clean content, no stale markers → ALLOW."""
        docs_path = os.path.join(self.repo, "docs", "feature.md")
        os.makedirs(os.path.dirname(docs_path), exist_ok=True)
        with open(docs_path, "w", encoding="utf-8") as f:
            f.write("# Feature\nShipped and working.\n")
        _git(self.repo, "add", "docs/feature.md")
        _git(self.repo, "commit", "-m", "docs: feature shipped")

        card_body = """Type: docs
Files: docs/feature.md
Mode: modify-only
Tests: N/A
Acceptance:
- Verify: rg 'Shipped' docs/feature.md"""
        ok, err = chain.step_docs_head_verify(card_body, self.repo)
        self.assertTrue(ok, err)
        self.assertIsNone(err)

    def test_docs_head_verify_denies_stale_markers(self) -> None:
        """Docs card Verify: rg matches 'pending' → DENY."""
        docs_path = os.path.join(self.repo, "docs", "stale.md")
        os.makedirs(os.path.dirname(docs_path), exist_ok=True)
        with open(docs_path, "w", encoding="utf-8") as f:
            f.write("# Pending Work\npending backend-mode-aware-endpoints\n")
        _git(self.repo, "add", "docs/stale.md")
        _git(self.repo, "commit", "-m", "docs: stale reference still present")

        card_body = """Type: docs
Files: docs/stale.md
Tests: N/A
Acceptance:
- Verify: rg 'pending' docs/stale.md"""
        ok, err = chain.step_docs_head_verify(card_body, self.repo)
        self.assertFalse(ok)
        self.assertEqual(err, "E022_DOCS_STALE_MARKERS")

    def test_docs_head_verify_no_verify_lines_is_noop(self) -> None:
        """Card without Verify: lines → ALLOW (no-op)."""
        card_body = """Type: docs
Files: docs/foo.md
Tests: N/A"""
        ok, err = chain.step_docs_head_verify(card_body, self.repo)
        self.assertTrue(ok)
        self.assertIsNone(err)


if __name__ == "__main__":
    unittest.main()
