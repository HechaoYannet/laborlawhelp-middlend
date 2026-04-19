from fastapi.testclient import TestClient

from app.main import app


def test_playground_runtime_endpoint_exposes_debug_metadata() -> None:
    client = TestClient(app)

    response = client.get("/api/v1/playground/runtime")

    assert response.status_code == 200
    payload = response.json()
    assert payload["app_name"]
    assert payload["auth_mode"] in {"anonymous", "jwt"}
    assert payload["stream_path"] == "/api/v1/sessions/{session_id}/chat/stream"


def test_playground_static_page_is_served() -> None:
    client = TestClient(app)

    response = client.get("/playground/")

    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "全链路输入检查台" in response.text
