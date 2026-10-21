"""Declarative, ordered content transforms; never execute code from an archive."""

import math
from copy import deepcopy
from decimal import Decimal, InvalidOperation

from .schema import NAME
from .security import CmsError


def validate_steps(steps):
    if not isinstance(steps, list) or len(steps) > 100:
        raise CmsError("Transform steps must be a list of at most 100 operations.")
    for step in steps:
        if not isinstance(step, dict):
            raise CmsError("Each transform step must be an object.")
        op = step.get("op")
        allowed = {"rename": "to", "default": "value", "drop": None, "convert": "to"}
        if not isinstance(op, str) or op not in allowed:
            raise CmsError("Transforms support rename, default, drop, and convert.")
        path = step.get("path")
        if not isinstance(path, str) or not path or len(path) > 500 or any(not p for p in path.split(".")):
            raise CmsError("Transform path must be a dotted field path; use * for list items or locales.")
        if set(step) - {"op", "path", "typeKey", allowed[op]} or (allowed[op] and allowed[op] not in step):
            raise CmsError("Invalid transform arguments.")
        if "typeKey" in step and (not isinstance(step["typeKey"], str) or not NAME.fullmatch(step["typeKey"])):
            raise CmsError("Transform typeKey must be a content type key.")
        if op == "rename" and (not isinstance(step["to"], str) or not NAME.fullmatch(step["to"])):
            raise CmsError("Rename to must be a field name in the same object.")
        if op == "convert" and (not isinstance(step["to"], str) or step["to"] not in {"text", "number", "boolean"}):
            raise CmsError("Convert to must be text, number, or boolean.")


def _parents(value, parts, location="data"):
    if len(parts) == 1:
        if not isinstance(value, dict):
            raise CmsError(f"{location} must be an object for a transform.")
        if parts[0] == "*":
            for key in list(value):
                yield value, key, f"{location}.{key}"
        else:
            yield value, parts[0], f"{location}.{parts[0]}"
        return
    head, *tail = parts
    if head == "*":
        if isinstance(value, list):
            children = [(v, f"{location}[{i}]") for i, v in enumerate(value)]
        elif isinstance(value, dict):
            children = [(v, f"{location}.{k}") for k, v in value.items()]
        else:
            raise CmsError(f"{location} must be a list or object for *.")
        for child, path in children:
            yield from _parents(child, tail, path)
    elif isinstance(value, dict):
        if head in value and value[head] is not None:
            yield from _parents(value[head], tail, f"{location}.{head}")
    else:
        raise CmsError(f"{location} must be an object for a transform.")


def _convert(value, target, path):
    if value is None:
        return None
    if target == "text" and isinstance(value, (str, int, float, bool)):
        return str(value).lower() if isinstance(value, bool) else str(value)
    if target == "number" and not isinstance(value, bool) and isinstance(value, (str, int, float)):
        try:
            result = (
                value
                if isinstance(value, (int, float))
                else int(value)
                if value.strip().lstrip("+-").isdigit()
                else float(value)
            )
            if math.isfinite(result) and (not isinstance(value, str) or Decimal(value) == Decimal(str(result))):
                return result
        except (ValueError, OverflowError, InvalidOperation):
            pass
    if target == "boolean":
        if isinstance(value, bool):
            return value
        if isinstance(value, str) and value.lower() in {"true", "false"}:
            return value.lower() == "true"
    raise CmsError(f"Cannot convert {path} to {target}.", field_path=path)


def transform_data(data, steps, type_key=None, changes=None):
    validate_steps(steps)
    result = deepcopy(data)
    for index, step in enumerate(steps):
        if step.get("typeKey") and step["typeKey"] != type_key:
            continue
        for parent, key, path in _parents(result, step["path"].split(".")):
            op = step["op"]
            if op == "default":
                if key in parent:
                    continue
                parent[key] = deepcopy(step["value"])
            elif key not in parent:
                continue
            elif op == "rename":
                if step["to"] in parent:
                    raise CmsError(f"Cannot rename {path}: {step['to']} already exists.", field_path=path)
                parent[step["to"]] = parent.pop(key)
            elif op == "drop":
                del parent[key]
            elif op == "convert":
                parent[key] = _convert(parent[key], step["to"], path)
            if changes is not None:
                changes.append({"step": index, "op": op, "path": path})
    return result
