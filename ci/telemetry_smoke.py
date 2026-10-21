"""Verify a loopback Collector using synthetic SQLite content, OTLP and Prometheus."""

import argparse
import json
import os
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import urlsplit

os.environ.setdefault("MOSS_SECRET_KEY", "fixture-only-telemetry-secret-00000000000")
os.environ.setdefault("MOSS_SETUP_TOKEN", "fixture-only-telemetry-setup-token")

from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app


def loopback(value):
    endpoint = urlsplit(value)
    if (
        endpoint.scheme != "http"
        or endpoint.hostname not in {"localhost", "127.0.0.1"}
        or endpoint.username is not None
        or endpoint.password is not None
    ):
        raise ValueError("Smoke endpoints must use loopback HTTP without credentials")
    return value


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--endpoint", required=True, type=loopback)
    parser.add_argument("--metrics-url", required=True, type=loopback)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="moss-otel-smoke-") as directory:
        application = create_app(
            Settings(
                database_url=f"sqlite:///{directory}/fixture.db",
                use_sqlite=False,
                environment="development",
                skip_auth=False,
                secret="s" * 40,
                setup_token="t" * 30,
                storage_dir=Path(directory) / "media",
                otel_enabled=True,
                otel_endpoint=args.endpoint,
                otel_service_name="moss-telemetry-smoke",
                otel_sample_rate=1,
                otel_metric_interval_ms=1000,
            )
        )
        with TestClient(application) as client:
            response = client.post(
                "/auth/setup",
                json={
                    "token": "t" * 30,
                    "email": "fixture@example.invalid",
                    "password": "fixture-password-1234",
                    "name": "Fixture",
                },
            )
            assert response.status_code == 200
            account = client.get("/auth/me").json()
            headers = {"x-moss-project": account["projects"][0]["id"], "x-moss-csrf": account["csrf"]}

            def gql(query, variables=None, delivery=False, auth=None):
                response = client.post(
                    "/delivery/graphql" if delivery else "/graphql",
                    headers=auth or headers,
                    json={"query": query, "variables": variables},
                )
                assert response.status_code == 200
                return response.json()

            schema = gql(
                'mutation{saveContentType(key:"article",name:"Article",fields:[{name:"title",type:"text"},{name:"secret",type:"text",private:true}]){id}}'
            )
            assert not schema.get("errors"), schema
            saved = gql(
                'mutation($data:JSON!){saveEntry(typeKey:"article",slug:"fixture",data:$data,status:"published"){id}}',
                {"data": {"title": "PRIVATE_BODY_SENTINEL", "secret": "PRIVATE_FIELD_SENTINEL"}},
            )
            assert not saved.get("errors"), saved
            token = client.post(
                "/api/tokens", headers=headers, json={"name": "Fixture", "scopes": ["article"], "days": 1}
            ).json()["token"]
            auth = {"Authorization": f"Bearer {token}"}
            read = gql(
                'query PrivateOperationName {entries(typeKey:"article",filters:{title:"PRIVATE_BODY_SENTINEL"}){total}}',
                delivery=True,
                auth=auth,
            )
            assert read["data"]["entries"]["total"] == 1
            failed = gql("{allCmsArticle{secret}}", delivery=True, auth=auth)
            assert failed.get("errors")
            assert client.get("/health").status_code == 200
        deadline = time.monotonic() + 30
        while True:
            try:
                with urllib.request.urlopen(args.metrics_url, timeout=3) as response:
                    metrics = response.read().decode()
            except (urllib.error.URLError, TimeoutError):
                metrics = ""
            if "moss_graphql_errors_total" in metrics and 'http_route="/health"' in metrics:
                break
            if time.monotonic() > deadline:
                raise RuntimeError("Collector did not expose the expected request/GraphQL metrics")
            time.sleep(0.25)
        expected = (
            "http_server_request_duration_seconds_bucket",
            "db_client_operation_duration_seconds_bucket",
            "moss_graphql_operation_duration_seconds_bucket",
            "moss_operation_duration_seconds_bucket",
            "moss_graphql_errors_total",
        )
        assert all(name in metrics for name in expected)
        for secret in (
            "PRIVATE_BODY_SENTINEL",
            "PRIVATE_FIELD_SENTINEL",
            "PrivateOperationName",
            token,
            headers["x-moss-csrf"],
        ):
            assert secret not in metrics
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(
                {
                    "syntheticContent": True,
                    "backend": "sqlite",
                    "providerShutdownCompleted": True,
                    "prometheusMetricFamilies": list(expected),
                    "graphqlHttp200ErrorCounted": True,
                    "privateValuesExcluded": True,
                    "serviceInstanceLabel": 'service_instance_id="' in metrics,
                },
                indent=2,
            )
            + "\n"
        )
        selected = [
            line
            for line in metrics.splitlines()
            if line.startswith("#")
            or (
                'service_name="moss-telemetry-smoke"' in line
                and (
                    not line.startswith("db_")
                    or (
                        'moss_execution="request"' in line
                        and any(f'db_collection_name="{table}"' in line for table in ("entries", "entry_field_indexes"))
                    )
                )
            )
        ]
        args.output.with_suffix(".prom").write_text("\n".join(selected) + "\n")
    print(f"Telemetry smoke evidence: {args.output}")


if __name__ == "__main__":
    main()
