import pytest
from graphql import GraphQLSyntaxError, parse

from app.query_limits import bounded_query
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


@pytest.mark.parametrize("query", ["", "{", "{ leaf( }", "query Named { leaf } trailing"])
def test_parser_errors_propagate_unchanged(query):
    with pytest.raises(GraphQLSyntaxError) as expected:
        parse(query)
    with pytest.raises(GraphQLSyntaxError) as actual:
        bounded_query(query)
    assert actual.value.formatted == expected.value.formatted
