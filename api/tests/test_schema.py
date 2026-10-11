from copy import deepcopy
from types import SimpleNamespace

import pytest

from app.graphql import generated_schema, type_node
from app.schema import image_asset_ids, public_data, public_fields, reference_targets, validate_data, validate_fields
from app.security import CmsError


def test_localized_list_validation_keeps_the_full_error_path():
    fields = [{"name": "scores", "type": "list", "localized": True, "item": {"type": "number", "required": True}}]
    validate_fields(fields)
    validate_data(fields, {"scores": {"en": [0, 1.5]}}, None, "workspace")
    with pytest.raises(CmsError) as error:
        validate_data(fields, {"scores": {"en": [0, True]}}, None, "workspace")
    assert error.value.field_path == "data.scores.en[1]"


def test_public_projection_and_asset_resolution_exclude_nested_private_fields():
    fields = [
        {
            "name": "cards",
            "type": "list",
            "localized": True,
            "item": {
                "type": "object",
                "fields": [
                    {"name": "body", "type": "richText"},
                    {"name": "cover", "type": "asset"},
                    {"name": "notes", "type": "richText", "private": True},
                ],
            },
        }
    ]
    data = {"cards": {"en": [{"body": "![Cover](asset:public)", "cover": "public", "notes": "asset:secret"}]}}
    assert public_data(fields, data) == {"cards": {"en": [{"body": "![Cover](asset:public)", "cover": "public"}]}}
    assert image_asset_ids(fields, data) == ["public"]
    assert "notes" in data["cards"]["en"][0]


def test_reference_targets_include_nested_lists_and_reject_non_string_targets():
    fields = [
        {"name": "related", "type": "list", "item": {"type": "reference", "target": "article"}},
        {"name": "author", "type": "object", "fields": [{"name": "person", "type": "reference", "target": "person"}]},
    ]
    assert reference_targets(fields) == {"article", "person"}
    with pytest.raises(CmsError, match="Reference targets must be content type keys"):
        reference_targets([{"type": "reference", "target": ["article"]}])


def test_public_schema_projection_filters_nested_lists_without_mutating_the_source():
    fields = [
        {"name": "secret", "type": "text", "private": True},
        {
            "name": "groups",
            "type": "list",
            "localized": True,
            "item": {
                "type": "list",
                "item": {
                    "type": "object",
                    "fields": [
                        {"name": "title", "type": "text", "required": True},
                        {"name": "notes", "type": "text", "private": True},
                    ],
                },
            },
        },
    ]
    original = deepcopy(fields)
    projected = public_fields(fields)
    assert [f["name"] for f in projected] == ["groups"]
    assert projected[0]["localized"] is True
    assert projected[0]["item"]["item"]["fields"] == [{"name": "title", "type": "text", "required": True}]
    projected[0]["item"]["item"]["fields"][0]["name"] = "changed"
    assert fields == original


def test_metadata_and_generated_types_keep_private_fields_editorial_and_support_empty_public_objects():
    fields = [
        {"name": "secret", "type": "text", "private": True},
        {
            "name": "group",
            "type": "object",
            "fields": [{"name": "notes", "type": "text", "private": True}],
        },
    ]
    definition = SimpleNamespace(id="type", key="sample", name="Sample", version=1, fields=fields)
    assert type_node(definition, delivery=True).fields == [{"name": "group", "type": "object", "fields": []}]
    assert type_node(definition).fields == fields
    public = generated_schema([definition], delivery=True).as_str()
    assert "secret(locale:" not in public
    assert "notes(locale:" not in public
    assert "empty: Boolean!" in public
    editorial = generated_schema([definition]).as_str()
    assert "secret(locale:" in editorial
    assert "notes(locale:" in editorial
