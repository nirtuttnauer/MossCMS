from graphql import FragmentDefinitionNode, FragmentSpreadNode, OperationDefinitionNode, parse

from .security import CmsError

MAX_QUERY_DEPTH = 12
MAX_QUERY_SELECTIONS = 200


def bounded_query(query):
    document = parse(query)
    fragments = {d.name.value: d for d in document.definitions if isinstance(d, FragmentDefinitionNode)}
    count = 0

    def walk(selection_set, depth=0, seen=frozenset()):
        nonlocal count
        if not selection_set:
            return
        if depth > MAX_QUERY_DEPTH:
            raise CmsError("Query depth limit exceeded.", "QUERY_LIMIT")
        for node in selection_set.selections:
            count += 1
            if count > MAX_QUERY_SELECTIONS:
                raise CmsError("Query complexity limit exceeded.", "QUERY_LIMIT")
            if isinstance(node, FragmentSpreadNode):
                name = node.name.value
                if name in seen:
                    raise CmsError("Recursive fragment.", "QUERY_LIMIT")
                if name in fragments:
                    walk(fragments[name].selection_set, depth, seen | {name})
            else:
                walk(getattr(node, "selection_set", None), depth + 1, seen)

    for definition in document.definitions:
        if isinstance(definition, OperationDefinitionNode):
            walk(definition.selection_set)
