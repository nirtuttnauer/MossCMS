import time

import pytest
from graphql import GraphQLSyntaxError, parse

from app.query_limits import MAX_QUERY_CHARACTERS, MAX_QUERY_DEPTH, MAX_QUERY_SELECTIONS, bounded_query
from app.security import CmsError


def nested_query(selection_sets):
    return "{ node " * (selection_sets - 1) + "{ leaf }" + " }" * (selection_sets - 1)


def fields(count):
    return " ".join(f"q{i}: leaf" for i in range(count))


def assert_query_limit(query, message):
    with pytest.raises(CmsError) as error:
        bounded_query(query)
    assert str(error.value) == message
    assert error.value.extensions() == {"code": "QUERY_LIMIT"}


def test_depth_boundary_allows_leaf_without_a_selection_set():
    assert bounded_query(nested_query(13)) is None
    assert_query_limit(nested_query(14), "Query depth limit exceeded.")


def test_selection_count_boundary_counts_aliases():
    assert bounded_query("{ " + fields(200) + " }") is None
    assert_query_limit("{ " + fields(201) + " }", "Query complexity limit exceeded.")


def test_inline_fragments_count_as_selections():
    assert bounded_query("{ ... on Query { " + fields(199) + " } }") is None
    assert_query_limit("{ ... on Query { " + fields(200) + " } }", "Query complexity limit exceeded.")


def test_inline_fragments_increment_depth():
    assert bounded_query("{ ... on Query " + nested_query(12) + " }") is None
    assert_query_limit("{ ... on Query " + nested_query(13) + " }", "Query depth limit exceeded.")


def test_named_fragment_expansion_preserves_depth():
    assert bounded_query("{ ...Deep } fragment Deep on Query " + nested_query(13)) is None
    assert_query_limit("{ ...Deep } fragment Deep on Query " + nested_query(14), "Query depth limit exceeded.")


def test_repeated_fragments_count_each_spread_and_expansion():
    assert bounded_query("{ ...Fields ...Fields } fragment Fields on Query { " + fields(99) + " }") is None
    assert_query_limit(
        "{ ...Fields ...Fields leaf } fragment Fields on Query { " + fields(99) + " }",
        "Query complexity limit exceeded.",
    )


def test_shared_fragment_in_separate_branches_is_not_recursive():
    assert bounded_query("{ left { ...Fields } right { ...Fields } } fragment Fields on Query { leaf }") is None


@pytest.mark.parametrize(
    "fragments",
    [
        "fragment A on Query { ...A }",
        "fragment A on Query { ...B } fragment B on Query { ...A }",
        "fragment A on Query { node { ...A } }",
    ],
)
def test_recursive_fragments_are_rejected(fragments):
    assert_query_limit("{ ...A } " + fragments, "Recursive fragment.")


def test_unknown_fragment_is_counted_without_expansion():
    assert bounded_query("{ ...Missing " + fields(199) + " }") is None
    assert_query_limit("{ ...Missing " + fields(200) + " }", "Query complexity limit exceeded.")


def test_unused_fragments_are_not_traversed():
    assert bounded_query("{ leaf } fragment Unused on Query { ...Unused " + fields(201) + " }") is None
    assert bounded_query("fragment Unused on Query { ...Unused }") is None


def test_selection_count_accumulates_across_operations():
    query = "query First { " + fields(100) + " } query Second { " + fields(100) + " }"
    assert bounded_query(query) is None
    assert_query_limit(query + " query Third { leaf }", "Query complexity limit exceeded.")


def test_fragment_expansion_accumulates_across_operations():
    query = "query First { ...Fields } query Second { ...Fields } fragment Fields on Query { " + fields(99) + " }"
    assert bounded_query(query) is None
    assert_query_limit(query + " query Third { ...Fields }", "Query complexity limit exceeded.")


def hebrew_note(count):
    return fields(count) + ' note: leaf(text: "\\u05e9\\u05dc\\u05d5\\u05dd")'


def test_documented_caps_stay_at_the_same_bounds():
    assert (MAX_QUERY_DEPTH, MAX_QUERY_SELECTIONS, MAX_QUERY_CHARACTERS) == (12, 200, 30000)


def test_nested_fragment_expansion_counts_every_copy():
    inner = hebrew_note(97)
    fragments = "fragment A on Query { ...B ...B } fragment B on Query { " + inner + " }"
    assert bounded_query("{ ...A extra: leaf } " + fragments) is None
    assert_query_limit("{ ...A extra: leaf again: leaf } " + fragments, "Query complexity limit exceeded.")


def test_wide_fragment_expansion_is_rejected_quickly():
    leaf = 'fragment L0 on Query { leaf(text: "עברית") }'
    levels = [f"fragment L{level} on Query {{ " + " ".join([f"...L{level - 1}"] * 6) + " }" for level in range(1, 9)]
    query = "{ ...L8 } " + leaf + " " + " ".join(levels)
    assert len(query) < MAX_QUERY_CHARACTERS
    started = time.perf_counter()
    assert_query_limit(query, "Query complexity limit exceeded.")
    assert time.perf_counter() - started < 0.5


def test_hebrew_text_does_not_change_depth_accounting():
    opening = "{ node " * 12
    shallow = opening + '{ leaf(text: "עברית") }' + " }" * 12
    deeper = "{ node " + shallow + " }"
    assert bounded_query("{ ...Deep } fragment Deep on Query " + shallow) is None
    assert_query_limit("{ ...Deep } fragment Deep on Query " + deeper, "Query depth limit exceeded.")


def query_with_hebrew_text(characters):
    prefix = '{ leaf(text: "'
    suffix = '") }'
    return prefix + ("א" * (characters - len(prefix) - len(suffix))) + suffix


def test_hebrew_document_at_the_character_cap_still_parses():
    query = query_with_hebrew_text(MAX_QUERY_CHARACTERS)
    assert len(query) == 30000
    assert bounded_query(query) is None
    document = bounded_query(query, return_document=True)
    assert document.definitions[0].selection_set.selections[0].name.value == "leaf"


def test_oversized_hebrew_document_is_rejected_without_parsing(monkeypatch):
    def refuse_parse(*_args, **_kwargs):
        raise AssertionError("oversized document reached the parser")

    monkeypatch.setattr("app.query_limits.parse", refuse_parse)
    query = query_with_hebrew_text(MAX_QUERY_CHARACTERS + 1)
    assert len(query) == 30001
    started = time.perf_counter()
    assert_query_limit(query, "Query length limit exceeded.")
    assert time.perf_counter() - started < 0.5


def test_short_hebrew_query_is_accepted():
    assert bounded_query('{ leaf(text: "שלום עליכם") }') is None


@pytest.mark.parametrize("query", ["", "{", "{ leaf( }", "query Named { leaf } trailing"])
def test_parser_errors_propagate_unchanged(query):
    with pytest.raises(GraphQLSyntaxError) as expected:
        parse(query)
    with pytest.raises(GraphQLSyntaxError) as actual:
        bounded_query(query)
    assert actual.value.formatted == expected.value.formatted
