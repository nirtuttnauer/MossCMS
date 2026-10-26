"""Explicit capabilities. Classic roles keep today's access until a workspace opts in."""

import json
import re

from sqlalchemy import select

from .models import Membership, Project
from .schema import NAME
from .security import CmsError

CAPABILITIES = frozenset({"read", "create", "edit", "publish", "schedule", "review", "media", "schema", "team"})
CLASSIC_ROLES = frozenset({"admin", "editor", "reader"})
ASSIGNABLE_ROLES = CLASSIC_ROLES | {"author", "publisher"}
ROLE_CAPABILITIES = {
    "reader": frozenset({"read"}),
    "author": frozenset({"read", "create", "edit", "media"}),
    "editor": frozenset({"read", "create", "edit", "publish", "schedule", "review", "media"}),
    "publisher": frozenset({"read", "create", "edit", "publish", "schedule", "review", "media"}),
    "admin": CAPABILITIES,
}
ROLE_EXPLANATIONS = {
    "reader": "Can read drafts, history, and the publication queue. Cannot edit, publish, or upload media.",
    "author": "Can create and edit drafts and upload media. Cannot publish, schedule, or approve.",
    "editor": "Can edit, publish, schedule, review, and upload media. Cannot change schemas or membership.",
    "publisher": "Can edit, publish, schedule, review, and upload media. Cannot change schemas or membership.",
    "admin": "Can manage schemas, membership, tokens, and every content action. Field rules never remove administrator access.",
}
PATH = re.compile(r"^[a-zA-Z][a-zA-Z0-9_]*(?:\.(?:\*|[a-zA-Z][a-zA-Z0-9_]*))*$")


def capabilities_for(role, custom_permissions):
    if not custom_permissions and role not in CLASSIC_ROLES:
        return frozenset()
    return ROLE_CAPABILITIES.get(role, frozenset())


def ensure_access(context):
    if context.get("delivery"):
        context["capabilities"] = frozenset({"read"})
        context["custom_permissions"] = False
        context["field_rules"] = {}
        return context["capabilities"]
    if "capabilities" in context and "custom_permissions" in context:
        return context["capabilities"]
    session = context.get("session")
    project = session.get(Project, context.get("project_id")) if session and context.get("project_id") else None
    custom = bool(project and project.custom_permissions)
    context["custom_permissions"] = custom
    context["field_rules"] = dict(project.field_rules or {}) if project else {}
    context["capabilities"] = capabilities_for(context.get("role"), custom)
    return context["capabilities"]


def allowed_roles(custom_permissions):
    return ASSIGNABLE_ROLES if custom_permissions else CLASSIC_ROLES


def validate_field_rules(rules):
    if not isinstance(rules, dict):
        raise CmsError("Field rules must be an object.")
    encoded = json.dumps(rules)
    if len(encoded) > 20000:
        raise CmsError("Field rules are too large.")
    for type_key, roles in rules.items():
        if not isinstance(type_key, str) or not NAME.fullmatch(type_key) or not isinstance(roles, dict):
            raise CmsError("Field rules must be keyed by content type.")
        for role, access in roles.items():
            if role == "admin":
                raise CmsError("Field rules cannot remove administrator access.")
            if role not in ASSIGNABLE_ROLES or not isinstance(access, dict) or set(access) - {"read", "write"}:
                raise CmsError("Field rules support read and write lists for each role.")
            read = access.get("read", ["*"])
            write = access.get("write", ["*"])
            for mode, paths in (("read", read), ("write", write)):
                if not isinstance(paths, list) or any(not isinstance(path, str) for path in paths) or len(paths) > 100:
                    raise CmsError("Each field rule list can contain at most 100 paths.")
                if any(path != "*" and not PATH.fullmatch(path) for path in paths):
                    raise CmsError("Use field paths such as title, meta.note, or sections.*.caption.")
            if "*" not in read:
                for path in write:
                    if (
                        path != "*"
                        and path not in read
                        and not any(
                            path.startswith(item + ".") or item.startswith(path + ".") for item in read if item != "*"
                        )
                    ):
                        raise CmsError("Writable fields must also be readable.")
    return rules


def rule_paths(identity, type_key, mode):
    ensure_access(identity)
    if identity.get("delivery") or identity.get("role") == "admin" or not identity.get("custom_permissions"):
        return None
    access = (identity.get("field_rules") or {}).get(type_key, {}).get(identity.get("role") or "")
    if not isinstance(access, dict):
        return None
    paths = access.get(mode)
    if not paths or "*" in paths:
        return None
    return tuple(paths)


def path_permitted(path, allowed):
    if allowed is None:
        return True
    return any(item == path or path.startswith(item + ".") or item.startswith(path + ".") for item in allowed)


def field_visible(identity, definition, name):
    return path_permitted(name, rule_paths(identity, definition.key, "read"))


def redact(value, fields, prefix, allowed):
    if allowed is None or not isinstance(value, dict):
        return value
    result = {}
    for field in fields:
        name = field["name"]
        path = f"{prefix}.{name}" if prefix else name
        if name not in value or not path_permitted(path, allowed):
            continue
        raw = value[name]
        if field["type"] == "object" and isinstance(raw, dict):
            result[name] = redact(raw, field.get("fields") or [], path, allowed)
        elif field["type"] == "list" and isinstance(raw, list) and (field.get("item") or {}).get("type") == "object":
            child = path + ".*"
            result[name] = [
                redact(item, field["item"].get("fields") or [], child, allowed) if isinstance(item, dict) else item
                for item in raw
            ]
        else:
            result[name] = raw
    return result


def merge_write(stored, incoming, fields, prefix, writable):
    stored = stored if isinstance(stored, dict) else {}
    incoming = incoming if isinstance(incoming, dict) else {}
    if writable is None:
        return incoming
    result = {}
    for field in fields:
        name = field["name"]
        path = f"{prefix}.{name}" if prefix else name
        if not path_permitted(path, writable):
            if name in stored:
                result[name] = stored[name]
            continue
        if field["type"] == "object":
            result[name] = merge_write(stored.get(name), incoming.get(name), field.get("fields") or [], path, writable)
        elif field["type"] == "list" and (field.get("item") or {}).get("type") == "object":
            child = path + ".*"
            rows = incoming.get(name, stored.get(name))
            stored_rows = stored.get(name) if isinstance(stored.get(name), list) else []
            if isinstance(rows, list):
                result[name] = [
                    merge_write(
                        stored_rows[index] if index < len(stored_rows) else {},
                        item,
                        field["item"].get("fields") or [],
                        child,
                        writable,
                    )
                    if isinstance(item, dict)
                    else item
                    for index, item in enumerate(rows)
                ]
        elif name in incoming:
            result[name] = incoming[name]
        elif name in stored:
            result[name] = stored[name]
    return result


def present_snapshot(identity, definition, snapshot):
    if not isinstance(snapshot, dict) or identity.get("delivery"):
        return snapshot
    allowed = rule_paths(identity, definition.key, "read")
    data = redact(snapshot.get("data") or {}, definition.fields, "", allowed)
    title = snapshot.get("slug") if not field_visible(identity, definition, "title") else snapshot.get("title")
    return {**snapshot, "data": data, "title": title}


def member_capabilities(session, project, user_id):
    membership = session.get(Membership, (project.id, user_id))
    if not membership:
        return None
    return capabilities_for(membership.role, project.custom_permissions)


def hidden_title_type_ids(session, identity):
    ensure_access(identity)
    if not identity.get("custom_permissions") or identity.get("role") == "admin":
        return []
    from .models import ContentType

    hidden = []
    for definition in session.scalars(
        select(ContentType).where(ContentType.project_id == identity["project_id"])
    ).all():
        if not field_visible(identity, definition, "title"):
            hidden.append(definition.id)
    return hidden
