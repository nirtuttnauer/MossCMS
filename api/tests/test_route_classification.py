"""Router exposure: every route is public or private, and the doc table matches."""

import os
import re

from scripts.classify_routes import (
    DOC,
    MissingRoute,
    RouteKey,
    UnclassifiedRoute,
    assert_closed,
    classify,
    documented_table,
    load_app,
    render_table,
    route_keys,
)

SECTION_START = "## Private admin and public delivery"
SECTION_END = "## Check the headers with curl"


def test_documented_table_matches_the_router():
    keys = route_keys(load_app())
    classified = classify(keys)
    assert documented_table() == render_table(classified)
    assert classified[RouteKey("GET", "/health")] == "public"
    assert classified[RouteKey("POST", "/delivery/graphql")] == "public"
    assert classified[RouteKey("GET", "/media/{id}")] == "public"
    assert classified[RouteKey("GET", "/media/{id}/variant/{width}")] == "public"
    assert classified[RouteKey("POST", "/api/preview/redeem")] == "private"
    assert classified[RouteKey("GET", "/openapi.json")] == "private"
    assert classified[RouteKey("GET", "/docs")] == "private"
    assert classified[RouteKey("POST", "/graphql")] == "private"
    assert all(kind == "public" for key, kind in classified.items() if key.path.startswith("/delivery/"))


def test_load_app_leaves_the_process_environment_unchanged():
    before = dict(os.environ)
    load_app()
    assert dict(os.environ) == before


def test_unclassified_route_fails():
    keys = route_keys(load_app())
    keys.append(RouteKey("GET", "/moss059-unclassified"))
    try:
        classify(keys)
    except UnclassifiedRoute as error:
        assert "/moss059-unclassified" in str(error)
    else:
        raise AssertionError("a route with no class was accepted")


def test_classified_route_missing_from_the_router_fails():
    keys = route_keys(load_app())
    classification = classify(keys)
    shrunk = [key for key in keys if key != RouteKey("GET", "/metrics")]
    try:
        assert_closed(classification, shrunk)
    except MissingRoute as error:
        assert "GET /metrics" in str(error)
    else:
        raise AssertionError("a classified route missing from the router was accepted")


def test_private_admin_section_wording():
    text = DOC.read_text()
    section = text[text.index(SECTION_START) : text.index(SECTION_END)].lower()
    for phrase in ("compliant", "compliance", "guarantees", "only one", "more secure than"):
        assert phrase not in section
    assert re.search(r"\bfirst\b", section) is None
