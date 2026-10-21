"""Operator commands for migrations, recovery, seeding, and serving the app."""

import argparse
import json
import os
import zipfile
from pathlib import Path
from types import SimpleNamespace

from dotenv import load_dotenv
from fastapi import HTTPException
from sqlalchemy import select

from .config import Settings
from .content import save_entry, save_type
from .migrate import migrate
from .models import Membership, Project, Token, User, database
from .development import DEVELOPMENT_USER_ID
from .security import audit, issue_token


def main():
    load_dotenv()
    parser = argparse.ArgumentParser(description="MossCMS operator tools")
    parser.add_argument(
        "command",
        choices=["serve", "migrate", "reindex", "reset-password", "claim-workspace", "seed", "export", "import"],
    )
    parser.add_argument("--email")
    parser.add_argument("--project")
    parser.add_argument("--file", type=Path, help="Workspace archive path")
    parser.add_argument("--pipeline", type=Path, help="Import transform JSON")
    parser.add_argument("--include-private", action="store_true", help="Include private content in an export")
    parser.add_argument("--history", action="store_true", help="Include revision history in an export")
    parser.add_argument("--apply", action="store_true", help="Commit an import (the default is a dry run)")
    args = parser.parse_args()
    settings = Settings().validate()
    engine, factory = database(settings.database_url)
    try:
        if args.command in {"migrate", "serve"}:
            migrate(engine)
        if args.command == "serve":
            import uvicorn

            uvicorn.run(
                "app.main:app",
                host="0.0.0.0",
                port=int(os.getenv("PORT", os.getenv("MOSS_PORT", "8001"))),
                log_level="info",
                timeout_graceful_shutdown=20,
            )
        elif args.command in {"export", "import"}:
            from .portability import export_workspace, import_workspace, _load
            from .security import CmsError

            if not args.project or not args.email or not args.file:
                parser.error("--project, --email, and --file are required for workspace migration")
            if args.command == "export" and (args.apply or args.pipeline):
                parser.error("--apply and --pipeline are import options")
            if args.command == "import" and (args.include_private or args.history):
                parser.error("--include-private and --history are export options")
            try:
                if args.command == "export":
                    report = export_workspace(
                        factory,
                        settings,
                        args.project,
                        args.email,
                        args.file,
                        include_private=args.include_private,
                        history=args.history,
                    )
                else:
                    pipeline = _load(args.pipeline.read_bytes()) if args.pipeline else None
                    report = import_workspace(
                        factory, settings, args.project, args.email, args.file, pipeline=pipeline, apply=args.apply
                    )
            except (CmsError, OSError, ValueError, zipfile.BadZipFile, HTTPException) as error:
                parser.error(str(error))
            print(json.dumps(report, ensure_ascii=False))
        elif args.command == "reset-password":
            if not args.email:
                parser.error("--email is required")
            with factory.begin() as session:
                user = session.scalar(select(User).where(User.email == args.email.strip().lower()))
                if not user:
                    parser.error("Account not found")
                for existing in session.scalars(select(Token).where(Token.kind == "reset", Token.user_id == user.id)):
                    session.delete(existing)
                raw, _ = issue_token(session, "reset", days=1, user_id=user.id, email=user.email)
                audit(session, None, "operator", "account.recovery.issue", userId=user.id)
                print(settings.public_url + "/#reset/" + raw)
        elif args.command == "reindex":
            if not args.project:
                parser.error("--project is required; reindexing is limited to one workspace")
            from .indexing import rebuild
            from .models import Entry, EntryFieldIndex

            with factory.begin() as session:
                if not session.get(Project, args.project):
                    parser.error("Workspace not found")
                count = rebuild(session.connection(), Entry.__table__, EntryFieldIndex.__table__, args.project)
                print(json.dumps({"reindexed": args.project, "entries": count}))
        elif args.command == "claim-workspace":
            if not args.email or not args.project:
                parser.error("--email and --project are required; recovery is limited to one unowned workspace")
            with factory.begin() as session:
                project = session.scalar(select(Project).where(Project.id == args.project).with_for_update())
                if not project:
                    parser.error("Workspace not found")
                if session.scalar(select(Membership.user_id).where(Membership.project_id == project.id).limit(1)):
                    parser.error("Workspace already has members; ask its administrator for an invitation")
                user = session.scalar(select(User).where(User.email == args.email.strip().lower()))
                if not user or user.id == DEVELOPMENT_USER_ID:
                    parser.error("Real administrator account not found")
                session.add(Membership(project_id=project.id, user_id=user.id, role="admin"))
                audit(session, project.id, "operator", "project.claim", userId=user.id)
                print(json.dumps({"claimed": project.id, "administrator": user.email}))
        elif args.command == "seed":
            if not args.project:
                parser.error("--project is required; seeding is always explicit")
            with factory.begin() as session:
                member = session.scalar(
                    select(Membership).where(Membership.project_id == args.project, Membership.role == "admin").limit(1)
                )
                if not member:
                    parser.error("Project administrator not found")
                c = {
                    "project_id": args.project,
                    "role": "admin",
                    "actor": "seed",
                    "user": session.get(User, member.user_id),
                    "token": SimpleNamespace(csrf="seed"),
                    "request": SimpleNamespace(headers={"x-moss-csrf": "seed"}),
                    "delivery": False,
                }
                from .models import ContentType, Entry

                definition = session.scalar(
                    select(ContentType).where(ContentType.project_id == args.project, ContentType.key == "article")
                )
                if not definition:
                    save_type(
                        session,
                        c,
                        "article",
                        "Article",
                        [{"name": "title", "type": "text", "required": True}, {"name": "body", "type": "richText"}],
                    )
                if not session.scalar(
                    select(Entry.id).where(Entry.project_id == args.project, Entry.slug == "welcome")
                ):
                    save_entry(
                        session,
                        c,
                        "article",
                        "welcome",
                        {"title": "Welcome to MossCMS", "body": "Your content API is ready."},
                        "published",
                    )
                print(json.dumps({"seeded": args.project}))
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
