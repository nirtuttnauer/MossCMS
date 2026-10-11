from fastapi.testclient import TestClient

import app.main as main


def test_brand_assets_are_served_without_exposing_other_files(app, tmp_path, monkeypatch):
    brand = tmp_path / "static" / "brand"
    brand.mkdir(parents=True)
    (brand / "logo.png").write_bytes(b"logo-content")
    (tmp_path / "private.txt").write_text("private")
    monkeypatch.setattr(main, "__file__", str(tmp_path / "app" / "main.py"))

    with TestClient(main.create_app(app.state.settings)) as client:
        response = client.get("/brand/logo.png")
        assert response.status_code == 200
        assert response.content == b"logo-content"
        assert response.headers["content-type"] == "image/png"
        assert client.get("/brand/missing.png").status_code == 404
        assert client.get("/brand/..%2F..%2Fprivate.txt").status_code == 404
