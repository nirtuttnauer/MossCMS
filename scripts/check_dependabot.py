#!/usr/bin/env python3
"""Check Dependabot coverage and validate .github/dependabot.yml.

The manifest set is every path from:

    git ls-files '*package.json' '*pyproject.toml' Dockerfile .github/workflows

plus nested Dockerfiles. The bare pathspec ``Dockerfile`` matches only the
repository root, so ``git ls-files '*Dockerfile'`` is unioned in. That covers
``example-site/Dockerfile``, whose base images are pinned to digests.

The YAML is checked against the vendored SchemaStore Dependabot 2.0 schema
(draft-07, https://json.schemastore.org/dependabot-2.0.json).

Version updates run monthly. Each ecosystem is one update entry with one group
matching every dependency, and ``open-pull-requests-limit`` is 3.
"""

import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / ".github" / "dependabot.yml"
SCHEMA_PATH = ROOT / ".github" / "dependabot-2.0.schema.json"
SCHEMA_SHA256 = "f310bfb4960eea6a5fb7d75de54ab49ba36f947757c8f4d5de88d3ea8ac51d3f"
TICKET_PATHSPECS = ["*package.json", "*pyproject.toml", "Dockerfile", ".github/workflows"]
EXPECTED_ECOSYSTEMS = ("uv", "npm", "github-actions", "docker")
OPEN_PULL_REQUEST_LIMIT = 3

_DOUBLE_ESCAPES = {
    '"': '"',
    "\\": "\\",
    "/": "/",
    "n": "\n",
    "r": "\r",
    "t": "\t",
    "b": "\b",
    "f": "\f",
}


class ParseError(ValueError):
    pass


def parse_yaml(text):
    """Parse the restricted YAML Dependabot config files use."""
    lines = []
    for number, raw in enumerate(text.splitlines(), 1):
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        indent = len(raw) - len(raw.lstrip(" "))
        if raw[:indent].strip(" ") or "\t" in raw[:indent]:
            raise ParseError(f"line {number}: only space indentation is supported")
        lines.append((indent, raw.strip(), number))
    if not lines:
        raise ParseError("empty YAML document")
    parser = _Parser(lines)
    value = parser.parse_value(lines[0][0])
    if parser.index != len(lines):
        indent, content, number = lines[parser.index]
        raise ParseError(f"line {number}: trailing content {content!r} at indent {indent}")
    return value


class _Parser:
    def __init__(self, lines):
        self.lines = lines
        self.index = 0

    def peek(self):
        if self.index >= len(self.lines):
            return None
        return self.lines[self.index]

    def parse_value(self, indent):
        peeked = self.peek()
        if peeked is None or peeked[0] != indent:
            raise ParseError("expected a nested value")
        if peeked[1].startswith("- ") or peeked[1] == "-":
            return self.parse_list(indent)
        return self.parse_map(indent)

    def parse_map(self, indent):
        result = {}
        while True:
            peeked = self.peek()
            if peeked is None or peeked[0] < indent or peeked[1].startswith("- ") or peeked[1] == "-":
                break
            if peeked[0] != indent:
                raise ParseError(f"line {peeked[2]}: expected indent {indent}")
            key, raw_value = _split_entry(peeked[1], peeked[2])
            if key in result:
                raise ParseError(f"line {peeked[2]}: duplicate key {key!r}")
            self.index += 1
            result[key] = self._nested_or_scalar(raw_value, indent)
        return result

    def parse_list(self, indent):
        items = []
        while True:
            peeked = self.peek()
            if peeked is None or peeked[0] != indent or not (peeked[1].startswith("- ") or peeked[1] == "-"):
                break
            content = peeked[1][2:].strip() if peeked[1].startswith("- ") else ""
            line = peeked[2]
            self.index += 1
            if content == "":
                items.append(self._nested_block(indent))
                continue
            if _is_mapping_entry(content):
                key, raw_value = _split_entry(content, line)
                item = {key: self._nested_or_scalar(raw_value, indent)}
                nxt = self.peek()
                if nxt is not None and nxt[0] > indent and not nxt[1].startswith("- ") and nxt[1] != "-":
                    extra = self.parse_map(nxt[0])
                    overlap = set(item) & set(extra)
                    if overlap:
                        raise ParseError(f"line {line}: duplicate keys {sorted(overlap)}")
                    item.update(extra)
                items.append(item)
            else:
                items.append(_parse_scalar(content, line))
        return items

    def _nested_or_scalar(self, raw_value, parent_indent):
        if raw_value == "":
            return self._nested_block(parent_indent)
        return _parse_scalar(raw_value, self.lines[self.index - 1][2])

    def _nested_block(self, parent_indent):
        nxt = self.peek()
        if nxt is None or nxt[0] <= parent_indent:
            return None
        return self.parse_value(nxt[0])


def _is_mapping_entry(content):
    if content[0] in "'\"":
        return False
    return re.match(r"[^:]+:( |$)", content) is not None


def _split_entry(content, line):
    if content.startswith('"') or content.startswith("'"):
        raise ParseError(f"line {line}: quoted keys are not supported")
    key, separator, raw_value = content.partition(":")
    if not separator:
        raise ParseError(f"line {line}: expected key: value")
    key = key.strip()
    if not key:
        raise ParseError(f"line {line}: empty key")
    return key, raw_value.strip()


def _parse_scalar(raw, line):
    text = raw.strip()
    if text.startswith('"'):
        value, rest = _read_double(text, line)
        _ensure_comment(rest, line)
        return value
    if text.startswith("'"):
        value, rest = _read_single(text, line)
        _ensure_comment(rest, line)
        return value
    if " #" in text:
        text = text.split(" #", 1)[0].rstrip()
    if text in ("true", "false"):
        return text == "true"
    if text in ("null", "~"):
        return None
    if text[:1] in "{[":
        raise ParseError(f"line {line}: flow collections are not supported")
    if re.fullmatch(r"-?(0|[1-9][0-9]*)", text):
        return int(text)
    return text


def _ensure_comment(rest, line):
    rest = rest.strip()
    if rest and not rest.startswith("#"):
        raise ParseError(f"line {line}: trailing content after scalar")


def _read_double(text, line):
    chars = []
    index = 1
    while index < len(text):
        char = text[index]
        if char == "\\":
            if index + 1 >= len(text):
                raise ParseError(f"line {line}: unfinished escape")
            escape = text[index + 1]
            if escape not in _DOUBLE_ESCAPES:
                raise ParseError(f"line {line}: unsupported escape \\{escape}")
            chars.append(_DOUBLE_ESCAPES[escape])
            index += 2
            continue
        if char == '"':
            return "".join(chars), text[index + 1 :]
        chars.append(char)
        index += 1
    raise ParseError(f"line {line}: unterminated double quote")


def _read_single(text, line):
    chars = []
    index = 1
    while index < len(text):
        char = text[index]
        if char == "'":
            if index + 1 < len(text) and text[index + 1] == "'":
                chars.append("'")
                index += 2
                continue
            return "".join(chars), text[index + 1 :]
        chars.append(char)
        index += 1
    raise ParseError(f"line {line}: unterminated single quote")


def _json_equal(left, right):
    if isinstance(left, bool) or isinstance(right, bool):
        return isinstance(left, bool) and isinstance(right, bool) and left == right
    if isinstance(left, dict) and isinstance(right, dict):
        return left.keys() == right.keys() and all(_json_equal(left[key], right[key]) for key in left)
    if isinstance(left, list) and isinstance(right, list):
        return len(left) == len(right) and all(_json_equal(a, b) for a, b in zip(left, right))
    if isinstance(left, (int, float)) and isinstance(right, (int, float)):
        return left == right
    return left == right and type(left) is type(right)


def _resolve(root, ref):
    if not isinstance(ref, str) or not ref.startswith("#/"):
        raise ParseError(f"only local schema references are supported, got {ref!r}")
    node = root
    for part in ref[2:].split("/"):
        part = part.replace("~1", "/").replace("~0", "~")
        node = node[int(part)] if isinstance(node, list) else node[part]
    return node


def _type_ok(instance, expected):
    names = expected if isinstance(expected, list) else [expected]

    def one(name):
        if name == "object":
            return isinstance(instance, dict)
        if name == "array":
            return isinstance(instance, list)
        if name == "string":
            return isinstance(instance, str)
        if name == "integer":
            return isinstance(instance, int) and not isinstance(instance, bool)
        if name == "number":
            return isinstance(instance, (int, float)) and not isinstance(instance, bool)
        if name == "boolean":
            return isinstance(instance, bool)
        if name == "null":
            return instance is None
        return False

    return any(one(name) for name in names)


def schema_errors(instance, schema):
    """Return draft-07 validation errors for the Dependabot schema."""
    return _validate(instance, schema, schema, "$")


def _validate(instance, schema, root, path):
    if schema is True:
        return []
    if schema is False:
        return [f"{path}: rejected by schema"]
    if not isinstance(schema, dict):
        raise ParseError(f"{path}: schema is not an object")
    if "$ref" in schema:
        return _validate(instance, _resolve(root, schema["$ref"]), root, path)
    errors = []
    for sub in schema.get("allOf", []):
        errors.extend(_validate(instance, sub, root, path))
    if "anyOf" in schema and not any(not _validate(instance, sub, root, path) for sub in schema["anyOf"]):
        errors.append(f"{path}: does not match any allowed form")
    if "oneOf" in schema:
        matches = sum(not _validate(instance, sub, root, path) for sub in schema["oneOf"])
        if matches != 1:
            errors.append(f"{path}: matches {matches} oneOf branches, expected 1")
    if "not" in schema and not _validate(instance, schema["not"], root, path):
        errors.append(f"{path}: should not match the negated schema")
    if "if" in schema:
        matched = not _validate(instance, schema["if"], root, path)
        branch = "then" if matched else "else"
        if branch in schema:
            errors.extend(_validate(instance, schema[branch], root, path))
    if "const" in schema and not _json_equal(instance, schema["const"]):
        errors.append(f"{path}: expected {schema['const']!r}")
    if "enum" in schema and not any(_json_equal(instance, choice) for choice in schema["enum"]):
        errors.append(f"{path}: {instance!r} is not an allowed value")
    if "type" in schema and not _type_ok(instance, schema["type"]):
        errors.append(f"{path}: expected type {schema['type']}, got {type(instance).__name__}")
        return errors
    if isinstance(instance, str):
        if "minLength" in schema and len(instance) < schema["minLength"]:
            errors.append(f"{path}: shorter than {schema['minLength']}")
        if "maxLength" in schema and len(instance) > schema["maxLength"]:
            errors.append(f"{path}: longer than {schema['maxLength']}")
        if "pattern" in schema and re.search(schema["pattern"], instance) is None:
            errors.append(f"{path}: does not match {schema['pattern']}")
    if isinstance(instance, (int, float)) and not isinstance(instance, bool):
        if "minimum" in schema and instance < schema["minimum"]:
            errors.append(f"{path}: below minimum {schema['minimum']}")
        if "maximum" in schema and instance > schema["maximum"]:
            errors.append(f"{path}: above maximum {schema['maximum']}")
    if isinstance(instance, list):
        if "minItems" in schema and len(instance) < schema["minItems"]:
            errors.append(f"{path}: fewer than {schema['minItems']} items")
        if "maxItems" in schema and len(instance) > schema["maxItems"]:
            errors.append(f"{path}: more than {schema['maxItems']} items")
        if schema.get("uniqueItems"):
            for left in range(len(instance)):
                for right in range(left + 1, len(instance)):
                    if _json_equal(instance[left], instance[right]):
                        errors.append(f"{path}: duplicate items")
        if "items" in schema:
            for index, item in enumerate(instance):
                errors.extend(_validate(item, schema["items"], root, f"{path}[{index}]"))
    if isinstance(instance, dict):
        if "minProperties" in schema and len(instance) < schema["minProperties"]:
            errors.append(f"{path}: fewer than {schema['minProperties']} properties")
        properties = schema.get("properties", {})
        required = schema.get("required", [])
        for key in required:
            if key not in instance:
                errors.append(f"{path}: missing required property {key}")
        for key, sub in properties.items():
            if key in instance:
                errors.extend(_validate(instance[key], sub, root, f"{path}.{key}"))
        additional = schema.get("additionalProperties", True)
        extra = [key for key in instance if key not in properties]
        if additional is False and extra:
            errors.append(f"{path}: unknown properties {extra}")
        elif isinstance(additional, dict):
            for key in extra:
                errors.extend(_validate(instance[key], additional, root, f"{path}.{key}"))
    return errors


def git_ls_files(pathspecs):
    completed = subprocess.run(
        ["git", "ls-files", *pathspecs],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        detail = completed.stderr.strip() or completed.stdout.strip() or "git ls-files failed"
        raise RuntimeError(detail)
    return [line for line in completed.stdout.splitlines() if line]


def manifest_paths():
    """Paths the ticket command lists, plus nested Dockerfiles."""
    ticket = git_ls_files(TICKET_PATHSPECS)
    dockerfiles = git_ls_files(["*Dockerfile"])
    return sorted(set(ticket) | set(dockerfiles))


def classify(path):
    """Return the Dependabot ecosystem and directory for a manifest path."""
    name = path.rsplit("/", 1)[-1]
    if name == "package.json":
        return "npm", _manifest_directory(path)
    if name == "pyproject.toml":
        return "uv", _manifest_directory(path)
    if name == "Dockerfile":
        return "docker", _manifest_directory(path)
    if path.startswith(".github/workflows/"):
        # github-actions scans .github/workflows from the repository root.
        return "github-actions", "/"
    raise ParseError(f"unexpected manifest path {path}")


def _manifest_directory(path):
    parent = path.rsplit("/", 1)[0] if "/" in path else ""
    if parent == "":
        return "/"
    return "/" + parent


def _normalize_directory(directory):
    if not isinstance(directory, str) or not directory.startswith("/"):
        return None
    if len(directory) > 1:
        directory = directory.rstrip("/")
    return directory or "/"


def entry_directories(entry):
    if "directories" in entry:
        values = entry["directories"]
        if not isinstance(values, list):
            return []
        return [_normalize_directory(value) for value in values]
    if "directory" in entry:
        return [_normalize_directory(entry["directory"])]
    return []


def coverage_problems(paths, updates):
    problems = []
    if not isinstance(updates, list):
        return ["updates must be a list"]
    for path in paths:
        try:
            ecosystem, directory = classify(path)
        except ParseError as exc:
            problems.append(str(exc))
            continue
        covered = False
        for entry in updates:
            if not isinstance(entry, dict) or entry.get("package-ecosystem") != ecosystem:
                continue
            if directory in entry_directories(entry):
                covered = True
                break
        if not covered:
            problems.append(f"{path} ({ecosystem} {directory}) is not covered by .github/dependabot.yml")
    return problems


def entry_policy_problems(index, entry):
    problems = []
    if not isinstance(entry, dict):
        return [f"updates[{index}] is not a mapping"]
    ecosystem = entry.get("package-ecosystem")
    schedule = entry.get("schedule")
    interval = schedule.get("interval") if isinstance(schedule, dict) else None
    if interval != "monthly":
        problems.append(f"updates[{index}] must use a monthly schedule")
    limit = entry.get("open-pull-requests-limit")
    if isinstance(limit, bool) or limit != OPEN_PULL_REQUEST_LIMIT:
        problems.append(f"updates[{index}] open-pull-requests-limit must be {OPEN_PULL_REQUEST_LIMIT}")
    groups = entry.get("groups")
    patterns = None
    if isinstance(groups, dict):
        spec = groups.get(ecosystem)
        if isinstance(spec, dict):
            patterns = spec.get("patterns")
    if not isinstance(groups, dict) or set(groups) != {ecosystem} or patterns != ["*"]:
        problems.append(f"updates[{index}] must group the {ecosystem} ecosystem with patterns: ['*']")
    return problems


def policy_problems(updates):
    if not isinstance(updates, list):
        return ["updates must be a list"]
    problems = []
    seen = []
    for index, entry in enumerate(updates):
        problems.extend(entry_policy_problems(index, entry))
        if isinstance(entry, dict):
            seen.append(entry.get("package-ecosystem"))
    if sorted(item for item in seen if isinstance(item, str)) != sorted(EXPECTED_ECOSYSTEMS) or len(seen) != len(
        EXPECTED_ECOSYSTEMS
    ):
        problems.append("updates must contain one group for each ecosystem: " + ", ".join(EXPECTED_ECOSYSTEMS))
    return problems


def lockfile_problems(paths):
    problems = []
    seen = set()
    for path in paths:
        ecosystem, directory = classify(path)
        if ecosystem == "npm":
            lock = "package-lock.json"
        elif ecosystem == "uv":
            lock = "uv.lock"
        else:
            continue
        relative = lock if directory == "/" else f"{directory.lstrip('/')}/{lock}"
        if relative in seen:
            continue
        seen.add(relative)
        if not (ROOT / relative).is_file():
            problems.append(f"{path} needs {relative} so Dependabot can update the {ecosystem} manifest")
    return problems


def digest_problems(paths):
    problems = []
    for path in paths:
        ecosystem, _directory = classify(path)
        if ecosystem != "docker":
            continue
        froms = []
        for line in (ROOT / path).read_text().splitlines():
            stripped = line.strip()
            if stripped.startswith("FROM "):
                froms.append(stripped)
        if not froms:
            problems.append(f"{path} has no FROM instruction")
        for line in froms:
            image = line.split()[1]
            if "@sha256:" not in image:
                problems.append(f"{path} base image is not pinned to a digest: {line}")
    return problems


def load_schema():
    data = SCHEMA_PATH.read_bytes()
    digest = hashlib.sha256(data).hexdigest()
    if digest != SCHEMA_SHA256:
        raise ParseError(f"vendored Dependabot schema hash is {digest}, expected {SCHEMA_SHA256}")
    return json.loads(data)


def check():
    problems = []
    try:
        schema = load_schema()
        document = parse_yaml(CONFIG_PATH.read_text())
        paths = manifest_paths()
    except (OSError, ParseError, RuntimeError, json.JSONDecodeError) as exc:
        return [str(exc)]
    if not isinstance(document, dict):
        return ["dependabot.yml must be a mapping"]
    problems.extend(schema_errors(document, schema))
    if not paths:
        problems.append("git ls-files returned no manifests")
    updates = document.get("updates")
    problems.extend(coverage_problems(paths, updates))
    problems.extend(policy_problems(updates) if isinstance(updates, list) else [])
    problems.extend(lockfile_problems(paths))
    problems.extend(digest_problems(paths))
    return problems


def main():
    problems = check()
    if problems:
        print("\n".join(problems), file=sys.stderr)
        return 1
    paths = manifest_paths()
    print("dependabot.yml matches the Dependabot schema and covers:")
    for path in paths:
        ecosystem, directory = classify(path)
        print(f"  {ecosystem} {directory}  {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
