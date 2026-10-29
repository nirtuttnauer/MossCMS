#!/usr/bin/env python3
"""Compare CHANGELOG.md with merged commits after the public-guide baseline.

The Unreleased section has one bullet per user-visible change. Each bullet
links the pull request and cites the commits in ``git log <base>..<head>``.
Review evidence, this script, and the changelog file itself are not release
notes, so commits that touch only those paths are not required entries.
"""

import argparse
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CHANGELOG = ROOT / "CHANGELOG.md"
BASE = "3a87c73c8e925973608e373863813163b41f04a9"
IGNORED_PREFIXES = ("reviews/",)
IGNORED_PATHS = {"CHANGELOG.md", "scripts/check_changelog.py"}
CATEGORIES = {"Added", "Changed", "Deprecated", "Removed", "Fixed", "Security"}
PR_URL = re.compile(r"https://github\.com/nirtuttnauer/MossCMS/pull/(\d+)\b")
SHA = re.compile(r"\b([0-9a-f]{40})\b")
TICKET = re.compile(r"MOSS-\d+")
BULLET = re.compile(r"^- ")
CATEGORY = re.compile(r"^### ([A-Za-z]+)$")
LINK_DEF = re.compile(r"^\[[^\]]+\]: \S")


def fail(message: str) -> None:
    print(f"changelog check failed: {message}", file=sys.stderr)
    raise SystemExit(1)


def git(*args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        fail(f"git {' '.join(args)} failed: {result.stderr.strip()}")
    return result.stdout


def rev_list(base: str, head: str) -> list[str]:
    return [line for line in git("rev-list", f"{base}..{head}").splitlines() if line]


def parents(commit: str) -> list[str]:
    return [line for line in git("rev-parse", f"{commit}^@").splitlines() if line]


def names(*revisions: str) -> set[str]:
    return {line for line in git("diff", "--name-only", *revisions).splitlines() if line}


def interesting(paths: set[str]) -> set[str]:
    kept = set()
    for path in paths:
        if path in IGNORED_PATHS or path.startswith(IGNORED_PREFIXES):
            continue
        kept.add(path)
    return kept


def user_visible(commits: list[str]) -> set[str]:
    """Commits whose own diff is a release note, excluding merge bookkeeping."""
    parent_map = {commit: parents(commit) for commit in commits}
    non_merge: dict[str, set[str]] = {}
    for commit, commit_parents in parent_map.items():
        if len(commit_parents) > 1:
            continue
        if not commit_parents:
            raw = {
                line
                for line in git("diff-tree", "--no-commit-id", "--name-only", "-r", "--root", commit).splitlines()
                if line
            }
        else:
            raw = names(commit_parents[0], commit)
        paths = interesting(raw)
        if paths:
            non_merge[commit] = paths

    visible = set(non_merge)
    for commit, commit_parents in parent_map.items():
        if len(commit_parents) < 2:
            continue
        first = commit_parents[0]
        merged = interesting(names(first, commit))
        if not merged:
            continue
        branch: set[str] = set()
        for parent in commit_parents[1:]:
            branch |= interesting(names(f"{first}...{parent}"))
        unique = merged - branch
        if unique:
            visible.add(commit)
            continue
        covered = all(any(path in paths for paths in non_merge.values()) for path in branch)
        if branch and not covered:
            visible.add(commit)
    return visible


def unreleased_lines(text: str) -> list[str]:
    if TICKET.search(text):
        fail("ticket ids belong in the commit message, not CHANGELOG.md")
    lines = text.splitlines()
    headings = [index for index, line in enumerate(lines) if line.startswith("## ")]
    unreleased = [index for index in headings if lines[index] == "## [Unreleased]"]
    if len(unreleased) != 1:
        fail("CHANGELOG.md must contain one ## [Unreleased] section")
    if any(lines[index].startswith("## [") and lines[index] != "## [Unreleased]" for index in headings):
        fail("CHANGELOG.md must not contain a released version section")
    start = unreleased[0] + 1
    end = next((index for index in headings if index > start), len(lines))
    section = lines[start:end]
    for line in section:
        if line == "" or BULLET.match(line) or LINK_DEF.match(line):
            continue
        category = CATEGORY.match(line)
        if category and category.group(1) in CATEGORIES:
            continue
        fail(f"Unreleased line is not a category, bullet, or link definition: {line}")
    bullets = [line for line in section if BULLET.match(line)]
    if not bullets:
        fail("Unreleased section has no entries")
    return bullets


def pull_request_commits(number: str, cache: dict[str, set[str]]) -> set[str]:
    if number in cache:
        return cache[number]
    result = subprocess.run(
        [
            "gh",
            "pr",
            "view",
            number,
            "--json",
            "commits,mergeCommit,state",
            "--jq",
            "[.commits[].oid, .mergeCommit.oid] | map(select(. != null)) | .[]",
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip()
        fail(f"could not read pull request {number}: {detail}")
    found = {line.strip() for line in result.stdout.splitlines() if line.strip()}
    if not found:
        fail(f"pull request {number} has no commits")
    cache[number] = found
    return found


def check_bullets(bullets: list[str], commits: set[str], visible: set[str]) -> None:
    cited: set[str] = set()
    cache: dict[str, set[str]] = {}
    for bullet in bullets:
        numbers = PR_URL.findall(bullet)
        shas = SHA.findall(bullet)
        if not numbers:
            fail(f"entry does not link its pull request: {bullet}")
        if not shas:
            fail(f"entry does not cite a commit: {bullet}")
        if len(shas) != len(set(shas)):
            fail(f"entry repeats a commit: {bullet}")
        owned: set[str] = set()
        for number in numbers:
            owned |= pull_request_commits(number, cache)
        for sha in shas:
            if sha not in commits:
                fail(f"{sha} is not a merged commit in the range")
            if sha not in visible:
                fail(f"{sha} is not a user-visible change in the range")
            if sha not in owned:
                fail(f"{sha} is not part of pull request {', '.join(numbers)}")
        for number in numbers:
            if not any(sha in pull_request_commits(number, cache) for sha in shas):
                fail(f"pull request {number} is not a commit cited on the same line")
        cited.update(shas)
    missing = sorted(visible - cited)
    if missing:
        fail("user-visible commits missing from CHANGELOG.md: " + ", ".join(missing))
    extra = sorted(cited - visible)
    if extra:
        fail("CHANGELOG.md cites commits that are not user-visible changes: " + ", ".join(extra))


def main() -> None:
    parser = argparse.ArgumentParser(description="Compare CHANGELOG.md with git log.")
    parser.add_argument("--base", default=BASE, help="Exclusive start commit (default: %(default)s)")
    parser.add_argument("--head", default="HEAD", help="Inclusive end commit (default: HEAD)")
    args = parser.parse_args()
    if not CHANGELOG.is_file():
        fail("CHANGELOG.md is missing")
    head = git("rev-parse", args.head).strip()
    base = git("rev-parse", args.base).strip()
    if base != BASE:
        fail(f"base {args.base} resolved to {base}, expected {BASE}")
    commits = set(rev_list(base, head))
    visible = user_visible(sorted(commits))
    bullets = unreleased_lines(CHANGELOG.read_text())
    check_bullets(bullets, commits, visible)
    print(f"changelog ok: {len(bullets)} entries, {len(visible)} user-visible commits, head {head}")


if __name__ == "__main__":
    main()
