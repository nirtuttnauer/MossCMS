import copy
import functools
import os
from unittest.mock import patch

import pytest

from app.security import CmsError
from app.transforms import transform_data
from conftest import define, entry, gql


def test_ordered_nested_transforms_do_not_mutate_input():
    data = {"items": [{"old": "12"}, {"old": "4"}], "localized": {"en": {"value": "true"}}}
    result = transform_data(
        data,
        [
            {"op": "rename", "path": "items.*.old", "to": "count"},
            {"op": "convert", "path": "items.*.count", "to": "number"},
            {"op": "default", "path": "items.*.flag", "value": False},
            {"op": "convert", "path": "localized.*.value", "to": "boolean"},
            {"op": "drop", "path": "items.*.flag"},
            {"op": "drop", "path": "items", "typeKey": "other"},
        ],
        "article",
    )
    assert result == {"items": [{"count": 12}, {"count": 4}], "localized": {"en": {"value": True}}}
    assert data["items"][0] == {"old": "12"}


def test_documented_steps_still_run():
    data = {"headline": "Stay", "items": [{"old": "4"}], "localized": {"en": {"value": "false"}}, "keep": True}
    nested = data["items"]

    def trap(*_args, **_kwargs):
        raise AssertionError("transform executed a payload")

    with patch("builtins.eval", trap), patch("builtins.exec", trap):
        result = transform_data(
            data,
            [
                {"op": "rename", "path": "headline", "to": "title"},
                {"op": "default", "path": "note", "value": "__import__('os').system('id')"},
                {"op": "default", "path": "sample", "value": "eval('1')"},
                {"op": "default", "path": "dotted", "value": "os.system('id')"},
                {"op": "default", "path": "count", "value": 0},
                {"op": "default", "path": "delta", "value": -2},
                {"op": "default", "path": "ratio", "value": 1.5},
                {"op": "default", "path": "flag", "value": False},
                {"op": "default", "path": "empty", "value": None},
                {"op": "default", "path": "tags", "value": ["eval", "exec", "import"]},
                {"op": "default", "path": "meta", "value": {"import": "os", "call": "os.path.join"}},
                {"op": "convert", "path": "items.*.old", "to": "number"},
                {"op": "convert", "path": "localized.*.value", "to": "boolean"},
                {"op": "rename", "path": "items.*.old", "to": "eval"},
                {"op": "drop", "path": "keep"},
                {"op": "default", "path": "skipped", "value": "nope", "typeKey": "other"},
            ],
            "article",
        )
    assert result == {
        "title": "Stay",
        "items": [{"eval": 4}],
        "localized": {"en": {"value": False}},
        "note": "__import__('os').system('id')",
        "sample": "eval('1')",
        "dotted": "os.system('id')",
        "count": 0,
        "delta": -2,
        "ratio": 1.5,
        "flag": False,
        "empty": None,
        "tags": ["eval", "exec", "import"],
        "meta": {"import": "os", "call": "os.path.join"},
    }
    assert data["headline"] == "Stay"
    assert data["items"] is nested
    assert data["items"][0] == {"old": "4"}
    assert data["keep"] is True


@pytest.mark.parametrize(
    "data,steps",
    [
        ({"old": 1, "new": 2}, [{"op": "rename", "path": "old", "to": "new"}]),
        ({"x": "maybe"}, [{"op": "convert", "path": "x", "to": "boolean"}]),
        ({"x": "NaN"}, [{"op": "convert", "path": "x", "to": "number"}]),
        ({"x": True}, [{"op": "convert", "path": "x", "to": "number"}]),
        ({"x": "9007199254740993.0"}, [{"op": "convert", "path": "x", "to": "number"}]),
        ({}, [{"op": "execute", "path": "x"}]),
        ({}, [{"op": [], "path": "x"}]),
        ({}, [{"op": "drop", "path": "x", "code": "arbitrary"}]),
    ],
)
def test_invalid_or_lossy_transforms_fail(data, steps):
    original = copy.deepcopy(data)
    with pytest.raises(CmsError):
        transform_data(data, steps)
    assert data == original


def _code_steps(kind, called):
    def payload(*_args, **_kwargs):
        called.append("call")
        return "ran"

    class RunsOnCopy:
        def __deepcopy__(self, memo):
            called.append("deepcopy")
            return self

        def __call__(self):
            called.append("call")
            return self

    class SpyList(list):
        def __iter__(self):
            called.append("iter")
            return list.__iter__(self)

    class SpyDict(dict):
        def get(self, key, default=None):
            called.append("get")
            return dict.get(self, key, default)

    rename = {"op": "rename", "path": "title", "to": "headline"}
    if kind == "op-eval":
        return [rename, {"op": "eval", "path": "title"}]
    if kind == "op-exec":
        return [rename, {"op": "exec", "path": "title", "code": "1"}]
    if kind == "op-import":
        return [rename, {"op": "import", "path": "os", "module": "os"}]
    if kind == "op-dunder-import":
        return [rename, {"op": "__import__", "path": "os"}]
    if kind == "op-os-system":
        return [rename, {"op": "os.system", "path": "title"}]
    if kind == "op-os-system-call":
        return [rename, {"op": "os.system('id')", "path": "title"}]
    if kind == "op-subprocess-call":
        return [rename, {"op": "subprocess.call", "path": "title", "args": ["id"]}]
    if kind == "text-eval":
        return [rename, "eval('1')"]
    if kind == "text-exec":
        return [rename, "exec('1')"]
    if kind == "text-import":
        return [rename, "import os"]
    if kind == "text-dunder-import":
        return [rename, "__import__('os')"]
    if kind == "text-dotted-call":
        return [rename, "os.path.join('a', 'b')"]
    if kind == "steps-are-eval":
        return eval
    if kind == "steps-are-text":
        return "exec('1')"
    if kind == "op-is-callable":
        return [rename, {"op": payload, "path": "title"}]
    if kind == "rename-to-dunder-import":
        return [{"op": "rename", "path": "title", "to": "__import__"}]
    if kind == "rename-to-dotted-call":
        return [{"op": "rename", "path": "title", "to": "os.system('id')"}]
    if kind == "exec-extra-key":
        return [rename, {"op": "drop", "path": "title", "exec": "1"}]
    if kind == "value-callable":
        return [rename, {"op": "default", "path": "injected", "value": payload}]
    if kind == "value-builtin-eval":
        return [rename, {"op": "default", "path": "injected", "value": eval}]
    if kind == "value-builtin-exec":
        return [rename, {"op": "default", "path": "injected", "value": exec}]
    if kind == "value-builtin-import":
        return [rename, {"op": "default", "path": "injected", "value": __import__}]
    if kind == "value-partial":
        return [rename, {"op": "default", "path": "injected", "value": functools.partial(payload)}]
    if kind == "value-nested":
        return [rename, {"op": "default", "path": "injected", "value": {"run": payload, "ok": 1}}]
    if kind == "value-list":
        return [rename, {"op": "default", "path": "injected", "value": [payload, "eval"]}]
    if kind == "value-module":
        return [rename, {"op": "default", "path": "injected", "value": os}]
    if kind == "value-code":
        return [rename, {"op": "default", "path": "injected", "value": compile("1", "<payload>", "eval")}]
    if kind == "value-copy-hook":
        return [rename, {"op": "default", "path": "injected", "value": RunsOnCopy()}]
    if kind == "spy-list":
        return SpyList([rename, {"op": "drop", "path": "keep"}])
    if kind == "spy-dict":
        return [SpyDict({"op": "drop", "path": "title"})]
    raise AssertionError(kind)


@pytest.mark.parametrize(
    "kind",
    [
        "op-eval",
        "op-exec",
        "op-import",
        "op-dunder-import",
        "op-os-system",
        "op-os-system-call",
        "op-subprocess-call",
        "text-eval",
        "text-exec",
        "text-import",
        "text-dunder-import",
        "text-dotted-call",
        "steps-are-eval",
        "steps-are-text",
        "op-is-callable",
        "rename-to-dunder-import",
        "rename-to-dotted-call",
        "exec-extra-key",
        "value-callable",
        "value-builtin-eval",
        "value-builtin-exec",
        "value-builtin-import",
        "value-partial",
        "value-nested",
        "value-list",
        "value-module",
        "value-code",
        "value-copy-hook",
        "spy-list",
        "spy-dict",
    ],
)
def test_code_execution_steps_are_rejected_without_mutating_input(kind):
    called = []
    data = {"title": "Stay", "nested": {"n": 1}, "keep": True}
    nested = data["nested"]
    original = copy.deepcopy(data)
    changes = []
    with pytest.raises(CmsError):
        transform_data(data, _code_steps(kind, called), "article", changes)
    assert called == []
    assert changes == []
    assert data == original
    assert data["nested"] is nested


def test_existing_schema_migration_accepts_pipeline_steps(client, admin):
    define(client, admin, fields=[{"name": "amount", "type": "text"}])
    created = entry(client, admin, data={"amount": "12"}, status="published")["data"]["saveEntry"]
    result = gql(
        client,
        admin,
        'mutation($migration:JSON!){saveContentType(key:"article",name:"Article",version:1,fields:[{name:"count",type:"number"}],migration:$migration){version}}',
        {
            "migration": {
                "steps": [
                    {"op": "rename", "path": "amount", "to": "count"},
                    {"op": "convert", "path": "count", "to": "number"},
                ]
            }
        },
    )
    assert "errors" not in result, result
    result = gql(client, admin, "query($id:ID!){entry(id:$id){data publishedData}}", {"id": created["id"]})
    assert "errors" not in result, result
    assert result["data"]["entry"]["data"] == {"count": 12}
    assert result["data"]["entry"]["publishedData"] == {"count": 12}
