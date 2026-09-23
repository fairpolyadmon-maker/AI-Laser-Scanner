import sys
from fastapi.testclient import TestClient
from main import app

client = TestClient(app)

def test_endpoints():
    print("Testing / ...")
    r = client.get("/")
    assert r.status_code == 200
    print("Root response:", r.json())

    print("Testing /health ...")
    r = client.get("/health")
    assert r.status_code == 200
    print("Health response:", r.json())

    print("Testing /api/signal/current ...")
    r = client.get("/api/signal/current")
    assert r.status_code == 200
    print("Current signal:", r.json())

    print("Testing /api/patterns ...")
    r = client.get("/api/patterns")
    assert r.status_code == 200
    data = r.json()
    print(f"Patterns loaded: {data['total_patterns']} patterns verified!")

    print("ALL BASIC ENDPOINTS FUNCTIONING 100% OK!")

if __name__ == "__main__":
    test_endpoints()
