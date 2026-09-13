def test_create_and_list(client):
    r = client.post("/api/v1/parcels", json={
        "name": "Test Field",
        "geojson": {
            "type": "Feature",
            "geometry": {
                "type": "Polygon",
                "coordinates": [[[120.0, 28.9], [120.01, 28.9],
                                [120.01, 28.91], [120.0, 28.91], [120.0, 28.9]]]
            },
            "properties": {}
        }
    })
    assert r.status_code == 201
    data = r.json()
    assert data["name"] == "Test Field"
    assert data["id"]  # has a UUID
    assert 107.0 < data["area_ha"] < 109.0

    r2 = client.get("/api/v1/parcels")
    assert r2.status_code == 200
    assert len(r2.json()) >= 1

    parcel_id = data["id"]
    r3 = client.get(f"/api/v1/parcels/{parcel_id}")
    assert r3.status_code == 200

    r4 = client.delete(f"/api/v1/parcels/{parcel_id}")
    assert r4.status_code == 204


def test_preview_split(client):
    r = client.post("/api/v1/parcels", json={
        "name": "Split Field",
        "geojson": {
            "type": "Feature",
            "geometry": {
                "type": "Polygon",
                "coordinates": [[[120.0, 28.9], [120.02, 28.9],
                                [120.02, 28.91], [120.0, 28.91], [120.0, 28.9]]]
            },
            "properties": {}
        }
    })
    parcel_id = r.json()["id"]
    r2 = client.post(f"/api/v1/parcels/{parcel_id}/preview-split", json={
        "mode": "strip", "count": 2
    })
    assert r2.status_code == 200
    result = r2.json()
    assert "sub_parcels" in result
    assert len(result["sub_parcels"]) == 2
    areas = [part["area_ha"] for part in result["sub_parcels"]]
    assert all(area > 0 for area in areas)
    assert abs(areas[0] - areas[1]) < 0.01
