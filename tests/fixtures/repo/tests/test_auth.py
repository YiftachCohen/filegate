from app import run

def test_login_requires_auth(client):
    r = client.get("/admin")
    assert r.status_code == 403
