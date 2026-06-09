"""
API tests — SQLite in-memory, no Docker required.
Run: pytest tests/ -v
"""
import os
import sys
from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy import StaticPool
from sqlalchemy.orm import sessionmaker

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from database.models import Base  # noqa: E402
from database.connection import get_db  # noqa: E402
from app import app  # noqa: E402

TEST_DB = "sqlite://"
engine = create_engine(TEST_DB, connect_args={"check_same_thread": False}, poolclass=StaticPool)
TestSession = sessionmaker(bind=engine)


def override_db():
    db = TestSession()
    try:
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = override_db
Base.metadata.create_all(bind=engine)
client = TestClient(app)

USER = {
    "email": "test@lauradevine.com",
    "password": "Test1234!",
    "firm_name": "Laura Devine Immigration",
}


def get_token():
    client.post("/api/v1/auth/signup", json=USER)
    r = client.post(
        "/api/v1/auth/login",
        data={"username": USER["email"], "password": USER["password"]},
    )
    return r.json()["access_token"]


def test_health():
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_signup():
    r = client.post(
        "/api/v1/auth/signup",
        json={"email": "new@test.com", "password": "Pass123!", "firm_name": "Test"},
    )
    assert r.status_code == 201
    assert "access_token" in r.json()


def test_duplicate_signup():
    client.post("/api/v1/auth/signup", json={"email": "dup@test.com", "password": "Pass123!"})
    r = client.post("/api/v1/auth/signup", json={"email": "dup@test.com", "password": "Pass123!"})
    assert r.status_code == 400


def test_login():
    token = get_token()
    assert len(token) > 10


def test_me():
    token = get_token()
    r = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    assert r.json()["email"] == USER["email"]


def test_list_documents_empty():
    token = get_token()
    r = client.get("/api/v1/documents/", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    assert isinstance(r.json(), list)


def test_stats_empty():
    token = get_token()
    r = client.get("/api/v1/documents/stats/summary", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    assert r.json()["total"] >= 0


def test_upload_non_pdf():
    token = get_token()
    r = client.post(
        "/api/v1/documents/upload",
        files={"file": ("test.txt", b"hello", "text/plain")},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 400


def test_upload_pdf():
    token = get_token()
    minimal_pdf = b"%PDF-1.4\n1 0 obj\n<</Type /Catalog>>\nendobj\n%%EOF"
    with patch("api.routes.documents.process_document"):
        r = client.post(
            "/api/v1/documents/upload",
            files={"file": ("invoice.pdf", minimal_pdf, "application/pdf")},
            headers={"Authorization": f"Bearer {token}"},
        )
    assert r.status_code == 202
    assert "job_id" in r.json()


def test_get_doc_not_found():
    token = get_token()
    r = client.get("/api/v1/documents/99999", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 404


def test_search():
    token = get_token()
    r = client.get("/api/v1/documents/search?q=sharma", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200


def test_export_csv():
    token = get_token()
    r = client.get("/api/v1/documents/export", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    assert "text/csv" in r.headers["content-type"]


def test_hitl_queue():
    token = get_token()
    r = client.get("/api/v1/documents/hitl/queue", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200


def test_unauthorized():
    r = client.get("/api/v1/documents/")
    assert r.status_code == 401
