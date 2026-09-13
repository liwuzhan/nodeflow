def test_coordinate_frame_has_no_hardcoded_default(client):
    response = client.get("/api/v1/settings/coordinate-frame")
    assert response.status_code == 200
    assert response.json() == {
        "ready": False,
        "type": "ENU",
        "frame_id": None,
        "origin_source": None,
        "ref_lon": None,
        "ref_lat": None,
        "ref_alt": None,
        "revision": None,
        "updated_at": None,
    }


def test_coordinate_frame_is_versioned(client):
    payload = {
        "frame_id": "farm-base-01",
        "origin_source": "rtk_base_manual",
        "ref_lon": 120.12345678,
        "ref_lat": 30.12345678,
        "ref_alt": 18.42,
    }
    first = client.put("/api/v1/settings/coordinate-frame", json=payload)
    second = client.put("/api/v1/settings/coordinate-frame", json={**payload, "ref_alt": 18.43})
    assert first.status_code == 200
    assert first.json()["revision"] == 1
    assert second.json()["revision"] == 2
    assert second.json()["ref_alt"] == 18.43
