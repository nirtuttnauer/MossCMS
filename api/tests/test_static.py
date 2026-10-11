import mimetypes

from fastapi.testclient import TestClient

import app.main as main


def test_brand_assets_are_served_without_exposing_other_files(app, tmp_path, monkeypatch):
    brand = tmp_path / "static" / "brand"
    brand.mkdir(parents=True)
    (brand / "logo.png").write_bytes(b"logo-content")
    (brand / "artwork.webp").write_bytes(b"artwork-content")
    (tmp_path / "private.txt").write_text("private")
    monkeypatch.setattr(main, "__file__", str(tmp_path / "app" / "main.py"))
    mimetypes.init()
    monkeypatch.delitem(mimetypes.types_map, ".webp", raising=False)

    with TestClient(main.create_app(app.state.settings)) as client:
        response = client.get("/brand/logo.png")
        assert response.status_code == 200
        assert response.content == b"logo-content"
        assert response.headers["content-type"] == "image/png"
        artwork = client.get("/brand/artwork.webp")
        assert artwork.status_code == 200
        assert artwork.content == b"artwork-content"
        assert artwork.headers["content-type"] == "image/webp"
        assert client.get("/brand/missing.png").status_code == 404
        assert client.get("/brand/..%2F..%2Fprivate.txt").status_code == 404
