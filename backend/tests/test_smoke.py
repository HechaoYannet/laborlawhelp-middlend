from fastapi.testclient import TestClient

from app.main import app


def test_main_flow_smoke() -> None:
    client = TestClient(app)
    headers = {"X-Anonymous-Token": "anon-test"}

    case_resp = client.post("/api/v1/cases", json={"title": "t", "region_code": "xian"}, headers=headers)
    assert case_resp.status_code == 201
    case_id = case_resp.json()["id"]

    session_resp = client.post(f"/api/v1/cases/{case_id}/sessions", headers=headers)
    assert session_resp.status_code == 201
    session_id = session_resp.json()["id"]

    with client.stream(
        "POST",
        f"/api/v1/sessions/{session_id}/chat",
        json={"message": "被辞退了", "client_seq": 1, "attachments": []},
        headers=headers,
    ) as response:
        assert response.status_code == 200
        payload = "".join(response.iter_text())

    assert "event: message_start" in payload
    assert "event: content_delta" in payload
    assert "event: final" in payload
    assert "event: message_end" in payload
