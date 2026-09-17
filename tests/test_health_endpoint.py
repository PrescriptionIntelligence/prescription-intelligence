"""
Tests for the /health endpoint.

Verifies:
  - HTTP 200 + {"status": "healthy"} when the database is reachable.
  - HTTP 503 + {"status": "degraded"} when the database is unavailable.

These tests do NOT require a running PostgreSQL instance.
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.database import Base, get_db
from backend.main import app


# =========================================================
# Fixtures
# =========================================================


@pytest.fixture()
def healthy_client():
    """Client backed by an in-memory SQLite DB (DB available)."""
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Session = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)

    def override_db():
        db = Session()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_db
    client = TestClient(app, raise_server_exceptions=False)
    yield client
    app.dependency_overrides.pop(get_db, None)
    engine.dispose()


@pytest.fixture()
def degraded_client():
    """Client whose DB session always raises (simulates DB unavailable)."""

    def override_db_broken():
        raise Exception("Database connection refused")
        yield  # make it a generator

    # FastAPI Depends expects a callable that returns/yields a dependency.
    # We make a generator that raises immediately.
    def broken_db_generator():
        class _BrokenSession:
            def execute(self, *a, **kw):
                raise Exception("Database connection refused")

            def close(self):
                pass

        db = _BrokenSession()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = broken_db_generator
    client = TestClient(app, raise_server_exceptions=False)
    yield client
    app.dependency_overrides.pop(get_db, None)


# =========================================================
# Tests: healthy state
# =========================================================


class TestHealthEndpointHealthy:

    def test_status_code_200_when_db_available(self, healthy_client):
        response = healthy_client.get("/health")
        assert response.status_code == 200

    def test_status_is_healthy(self, healthy_client):
        response = healthy_client.get("/health")
        data = response.json()
        assert data["status"] == "healthy"

    def test_database_field_is_connected(self, healthy_client):
        response = healthy_client.get("/health")
        data = response.json()
        assert data["database"] == "connected"

    def test_version_field_present(self, healthy_client):
        response = healthy_client.get("/health")
        data = response.json()
        assert "version" in data
        assert isinstance(data["version"], str)

    def test_response_is_json(self, healthy_client):
        response = healthy_client.get("/health")
        # No exception means valid JSON was returned.
        data = response.json()
        assert isinstance(data, dict)


# =========================================================
# Tests: degraded state (DB unavailable)
# =========================================================


class TestHealthEndpointDegraded:

    def test_status_code_503_when_db_unavailable(self, degraded_client):
        response = degraded_client.get("/health")
        assert response.status_code == 503

    def test_status_is_degraded(self, degraded_client):
        response = degraded_client.get("/health")
        data = response.json()
        assert data["status"] == "degraded"

    def test_database_field_is_unavailable(self, degraded_client):
        response = degraded_client.get("/health")
        data = response.json()
        assert data["database"] == "unavailable"

    def test_version_field_present_even_when_degraded(self, degraded_client):
        response = degraded_client.get("/health")
        data = response.json()
        assert "version" in data

    def test_load_balancer_can_detect_unhealthy(self, degraded_client):
        """
        Regression: verifies that HTTP 503 (not 200) is returned when
        the database is unreachable, so load balancers and Kubernetes
        readiness probes can take the instance out of rotation.
        """
        response = degraded_client.get("/health")
        assert response.status_code != 200, (
            "Health endpoint must NOT return 200 when database is unavailable. "
            "Load balancers rely on non-2xx to detect degraded instances."
        )
