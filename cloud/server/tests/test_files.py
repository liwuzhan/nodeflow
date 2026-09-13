def test_download_path_not_found(client):
    r = client.get("/api/v1/download/paths/nonexistent.bin")
    assert r.status_code == 404
