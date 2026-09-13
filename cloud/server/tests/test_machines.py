def test_register_and_list(client):
    r = client.post("/api/v1/machines", json={
        "id": "tractor-01", "name": "Tractor 1", "machine_type": "tractor"
    })
    assert r.status_code == 201
    assert r.json()["status"] == "offline"

    r2 = client.get("/api/v1/machines")
    assert r2.status_code == 200
    assert len(r2.json()) >= 1

    r3 = client.delete("/api/v1/machines/tractor-01")
    assert r3.status_code == 204
