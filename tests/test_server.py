import pytest
from litestar.testing import TestClient
from server import app


class TestServer:
    def test_server_starts(self):
        """Test that the server can be created and basic health check works"""
        with TestClient(app=app) as client:
            response = client.get("/health")
            assert response.status_code == 200
            assert response.json() == {"status": "healthy"}

    def test_query_endpoint_exists(self):
        """Test that the query endpoint exists and accepts POST requests"""
        with TestClient(app=app) as client:
            response = client.post("/query", json={"word": "test"})
            # POST endpoint returns 201 Created by default in Litestar
            assert response.status_code == 201
            assert "Definition for 'test' not implemented yet" in response.text

    def test_count_endpoint(self):
        """Test that the count endpoint returns dictionary statistics"""
        with TestClient(app=app) as client:
            response = client.get("/count")
            assert response.status_code == 200
            data = response.json()
            # Should have mdx and mdd keys
            assert "mdx" in data
            assert "mdd" in data
            # Should be integers (could be 0 if dictionary not found)
            assert isinstance(data["mdx"], int)
            assert isinstance(data["mdd"], int)