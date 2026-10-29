"""Red-first checks for scripts/verify.sh.

A dirty tree, a planted failing test, a planted skip, and a planted vulnerable
dev package each make the script exit non-zero. checks.yml and the script list
the same commands.
"""

import importlib.util
import os
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CHECKS = ROOT / ".github" / "workflows" / "checks.yml"
SCRIPT = ROOT / "scripts" / "verify.sh"
REPORT = ROOT / "scripts" / "verify_report.py"


def load_report():
    spec = importlib.util.spec_from_file_location("verify_report", REPORT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def extract_ci_steps(text):
    """Return (working-directory, command) pairs for every run step in checks.yml."""
    chunks = []
    current = []
    for line in text.splitlines():
        if line.startswith("      - "):
            if current:
                chunks.append(current)
            current = [line]
        elif current:
            current.append(line)
    if current:
        chunks.append(current)
    steps = []
    for chunk in chunks:
        workdir = "."
        command = None
        index = 0
        while index < len(chunk):
            line = chunk[index]
            directory = re.match(r"^\s+working-directory:\s*(\S+)\s*$", line)
            if directory:
                workdir = directory.group(1)
            block = re.match(r"^\s+-?\s*run:\s*\|[+-]?\s*$", line)
            inline = re.match(r"^\s+-?\s*run:\s*([^|>].*)$", line)
            if block:
                raw = []
                index += 1
                key_indent = len(line) - len(line.lstrip(" "))
                while index < len(chunk):
                    nxt = chunk[index]
                    if nxt.strip() == "":
                        raw.append("")
                        index += 1
                        continue
                    indent = len(nxt) - len(nxt.lstrip(" "))
                    if indent <= key_indent:
                        break
                    raw.append(nxt)
                    index += 1
                while raw and raw[-1] == "":
                    raw.pop()
                indents = [len(item) - len(item.lstrip(" ")) for item in raw if item.strip()]
                cut = min(indents) if indents else 0
                command = "\n".join(item[cut:] if item else "" for item in raw)
                continue
            if inline:
                command = inline.group(1).strip()
            index += 1
        if command is not None:
            steps.append((workdir, command))
    return steps


def command_occurrences(script_lines, command):
    wanted = [line.strip() for line in command.splitlines() if line.strip()]
    stripped = [line.strip() for line in script_lines]
    found = []
    if not wanted:
        return found
    last = len(stripped) - len(wanted) + 1
    for index in range(last):
        if stripped[index : index + len(wanted)] == wanted:
            found.append(index)
    return found


def workdir_matches(script_lines, index, workdir):
    window = script_lines[max(0, index - 8) : index]
    pattern = rf"^step\s+{re.escape(workdir)}\b"
    return any(re.match(pattern, line.strip()) for line in window)


class VerifyTests(unittest.TestCase):
    def test_ci_commands_match_the_script(self):
        ci_steps = extract_ci_steps(CHECKS.read_text(encoding="utf-8"))
        script_lines = SCRIPT.read_text(encoding="utf-8").splitlines()
        self.assertGreaterEqual(len(ci_steps), 15)
        missing = []
        for workdir, command in ci_steps:
            occurrences = command_occurrences(script_lines, command)
            if workdir == ".":
                matched = bool(occurrences)
            else:
                matched = any(workdir_matches(script_lines, index, workdir) for index in occurrences)
            if not matched:
                missing.append((workdir, command))
        if missing:
            rendered = "\n\n".join(f"[{workdir}]\n{command}" for workdir, command in missing)
            self.fail("CI-only commands missing from scripts/verify.sh:\n" + rendered)
        text = SCRIPT.read_text(encoding="utf-8")
        for snippet in (
            "uv export --frozen --all-groups --no-emit-project",
            "pip-audit --progress-spinner off",
            "npm audit",
            "gitleaks detect --no-git --source",
            "postgres:17-alpine",
            "refusing to run on a dirty tree",
        ):
            self.assertIn(snippet, text)

    def test_skip_scanner_rejects_skips_and_allows_deselected(self):
        report = load_report()
        clean = "=========== 399 passed, 4 deselected, 6 warnings in 69.03s (0:01:09) ==========="
        self.assertEqual(report.skip_problems(clean), [])
        skipped = "398 passed, 1 skipped, 4 deselected in 60.00s"
        self.assertTrue(report.skip_problems(skipped))
        self.assertTrue(report.skip_problems("1 xfailed, 398 passed in 1.00s"))
        self.assertTrue(report.skip_problems("1 xpassed in 1.00s"))
        locked = "FAILED tests/test_concurrency.py::test_postgres_workers_skip_locked_rows_and_claim_once"
        self.assertEqual(report.skip_problems(locked), [])
        self.assertEqual(report.skip_problems("      Tests  317 passed (317)\n"), [])
        self.assertTrue(report.skip_problems("      Tests  316 passed | 1 skipped (317)\n"))
        node = "# tests 46\n# pass 46\n# fail 0\n# cancelled 0\n# skipped 0\n# todo 0\n"
        self.assertEqual(report.skip_problems(node), [])
        self.assertTrue(report.skip_problems(node.replace("# skipped 0", "# skipped 1")))
        self.assertTrue(report.skip_problems(node.replace("# todo 0", "# todo 1")))
        self.assertTrue(report.skip_problems("  1 skipped\n  1 passed (2.0s)\n"))

    def test_dirty_tree_exits_nonzero(self):
        worktree = self.make_worktree()
        self.sync_under_test(worktree)
        readme = worktree / "README.md"
        readme.write_text(readme.read_text(encoding="utf-8") + "\n", encoding="utf-8")
        proc = self.run_verify(worktree, "red-dirty", timeout=60)
        self.assertNotEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("dirty", proc.stderr.lower())
        self.assertFalse((worktree / "reviews" / "red-dirty").exists())

    def test_planted_failing_test_exits_nonzero(self):
        worktree = self.make_worktree()
        self.sync_under_test(worktree)
        planted = worktree / "api" / "tests" / "test_verify_planted_failure.py"
        planted.write_text("def test_planted_failure():\n    assert False\n", encoding="utf-8")
        self.commit_paths(worktree, [planted], "Plant a failing test")
        proc = self.run_verify(worktree, "red-fail", timeout=900)
        evidence = self.evidence(worktree, "red-fail")
        codes = self.exit_codes(evidence)
        self.assertNotEqual(proc.returncode, 0, proc.stderr[-4000:])
        self.assertNotEqual(codes.get("pytest-sqlite"), 0)
        self.assertNotIn("pytest-postgres", codes)
        log = (evidence / "pytest-sqlite.txt").read_text(encoding="utf-8", errors="replace")
        self.assertIn("test_planted_failure", log)

    def test_planted_skip_exits_nonzero(self):
        worktree = self.make_worktree()
        self.sync_under_test(worktree)
        planted = worktree / "api" / "tests" / "test_verify_planted_skip.py"
        planted.write_text(
            'import pytest\n\n\ndef test_planted_skip():\n    pytest.skip("planted")\n',
            encoding="utf-8",
        )
        self.commit_paths(worktree, [planted], "Plant a runtime skip")
        proc = self.run_verify(worktree, "red-skip", timeout=900)
        evidence = self.evidence(worktree, "red-skip")
        codes = self.exit_codes(evidence)
        detail = f"{proc.stderr[-4000:]}\n{codes}"
        self.assertNotEqual(proc.returncode, 0, detail)
        self.assertNotEqual(codes.get("pytest-sqlite"), 0, detail)
        self.assertNotIn("pytest-postgres", codes)
        log = (evidence / "pytest-sqlite.txt").read_text(encoding="utf-8", errors="replace")
        self.assertIn("planted", log)

    def test_planted_vulnerable_dev_package_exits_nonzero(self):
        # cookie 0.4.2 is a low advisory: npm audit --audit-level=high stays green
        # and the default npm audit, which includes devDependencies, exits non-zero.
        worktree = self.make_worktree()
        self.sync_under_test(worktree)
        subprocess.run(
            ["npm", "install", "cookie@0.4.2", "--save-dev", "--package-lock-only", "--ignore-scripts"],
            cwd=worktree / "web",
            check=True,
        )
        self.commit_paths(
            worktree,
            [worktree / "web" / "package.json", worktree / "web" / "package-lock.json"],
            "Plant a vulnerable dev package",
        )
        proc = self.run_verify(worktree, "red-vuln", timeout=2400)
        evidence = self.evidence(worktree, "red-vuln")
        codes = self.exit_codes(evidence)
        self.assertNotEqual(proc.returncode, 0, proc.stderr[-4000:])
        self.assertEqual(codes.get("web"), 0, codes)
        self.assertIn("npm-audit-web", codes)
        self.assertNotEqual(codes.get("npm-audit-web"), 0)
        self.assertNotIn("gitleaks", codes)
        audit = (evidence / "npm-audit-web.txt").read_text(encoding="utf-8", errors="replace")
        self.assertIn("cookie", audit.lower())

    def make_worktree(self):
        path = Path(tempfile.mkdtemp(prefix="moss054-"))
        subprocess.run(["git", "worktree", "add", "--detach", str(path), "HEAD"], cwd=ROOT, check=True)
        self.addCleanup(self.remove_worktree, path)
        return path

    def remove_worktree(self, path):
        subprocess.run(["git", "worktree", "remove", "--force", str(path)], cwd=ROOT, check=False)
        shutil.rmtree(path, ignore_errors=True)
        subprocess.run(["docker", "rm", "-f", "moss-verify-pg", "moss-otel-smoke"], check=False, capture_output=True)
        subprocess.run(
            ["docker", "compose", "-f", str(ROOT / "ci" / "compose.yaml"), "-p", "mosscms-smoke", "down", "--volumes"],
            check=False,
            capture_output=True,
        )

    def sync_under_test(self, worktree):
        for name in ("verify.sh", "verify_report.py"):
            source = ROOT / "scripts" / name
            dest = worktree / "scripts" / name
            dest.write_bytes(source.read_bytes())
            if name.endswith(".sh"):
                dest.chmod(0o755)
        subprocess.run(
            ["git", "add", "--", "scripts/verify.sh", "scripts/verify_report.py"],
            cwd=worktree,
            check=True,
        )
        status = subprocess.check_output(["git", "status", "--porcelain"], cwd=worktree, text=True)
        if status.strip():
            self.commit(worktree, "Copy verify.sh under test")

    def commit_paths(self, worktree, paths, message):
        relative = [str(Path(path).resolve().relative_to(worktree)) for path in paths]
        subprocess.run(["git", "add", "--", *relative], cwd=worktree, check=True)
        self.commit(worktree, message)

    def commit(self, worktree, message):
        subprocess.run(
            [
                "git",
                "-c",
                "user.email=moss-verify@example.invalid",
                "-c",
                "user.name=moss-verify",
                "commit",
                "-m",
                message,
            ],
            cwd=worktree,
            check=True,
        )

    def run_verify(self, worktree, label, timeout):
        env = os.environ.copy()
        env["PATH"] = f"{Path.home() / '.local' / 'bin'}{os.pathsep}{env.get('PATH', '')}"
        return subprocess.run(
            ["bash", str(worktree / "scripts" / "verify.sh"), label],
            cwd=worktree,
            env=env,
            text=True,
            capture_output=True,
            timeout=timeout,
        )

    def evidence(self, worktree, label):
        sha = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=worktree, text=True).strip()
        return worktree / "reviews" / label / sha[:7]

    def exit_codes(self, evidence):
        rows = {}
        path = evidence / "exit-codes.txt"
        if not path.is_file():
            return rows
        for line in path.read_text(encoding="utf-8").splitlines():
            name, code = line.rsplit(" ", 1)
            rows[name] = int(code)
        return rows


if __name__ == "__main__":
    unittest.main()
