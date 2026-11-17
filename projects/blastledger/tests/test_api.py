import copy
import json
from fastapi.testclient import TestClient
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def fixture(name):
    return json.loads((ROOT / "fixtures" / name).read_text(encoding="utf-8"))
from blastledger.api import app

client = TestClient(app)


def test_openapi_exposes_post_assess():
    schema = client.get("/openapi.json").json()
    assert "post" in schema["paths"]["/assess"]


def test_danger_http():
    response = client.post("/assess", json=fixture("danger.json"))
    assert response.status_code == 200
    assert response.json()["verdict"] == "BLOCK-RECOMMENDED"
    assert response.json()["input_hash"]


def test_healthy_http():
    assert client.post("/assess", json=fixture("healthy.json")).json()["verdict"] == "PASS"


def test_missing_fields_http_422():
    d = copy.deepcopy(fixture("healthy.json"))
    del d["change"]["id"]
    resp = client.post("/assess", json=d)
    assert resp.status_code == 422


def test_extra_fields_http_422():
    d = fixture("healthy.json")
    d["services"][0]["secret"] = "should-not-accept"
    resp = client.post("/assess", json=d)
    assert resp.status_code == 422


def test_malformed_json_http_400():
    assert client.post("/assess", data="{invalid", headers={"Content-Type": "application/json"}).status_code == 400


def test_large_body_http_413():
    payload = b"{" + b" " * (1024 * 1024 + 1) + b"}"
    resp = client.post("/assess", content=payload, headers={"Content-Type": "application/json"})
    assert resp.status_code == 413


def test_response_deterministic():
    d = fixture("healthy.json")
    assert client.post("/assess", json=d).json() == client.post("/assess", json=d).json()


def test_no_persistence_or_modify_api():
    assert client.post("/delete", json={}).status_code == 404
    assert client.get("/assess").status_code == 405


def test_nonfinite_json_constant_rejected():
    payload = json.dumps(fixture("healthy.json")).replace('"max_rps": 1000', '"max_rps": NaN')
    result = client.post("/assess", data=payload, headers={"Content-Type": "application/json"})
    assert result.status_code == 422
