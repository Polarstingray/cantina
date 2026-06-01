'''
Auth + multi-tenant isolation tests for Phase 2: every data route requires a
session, sessions behave, admin-only routes are gated, and one household can
never see another's data.
'''

from conftest import make_client


# --- the login gate --------------------------------------------------------

def test_data_routes_require_auth(anon_client) :
    for method, path in [("get", "/foods"), ("get", "/inventory"), ("get", "/menu"),
                         ("get", "/list"), ("get", "/spending"),
                         ("post", "/foods"), ("get", "/auth/me")] :
        kwargs = {"json": {}} if method == "post" else {}
        r = getattr(anon_client, method)(path, **kwargs)
        assert r.status_code == 401, f"{method} {path} should be 401, got {r.status_code}"


def test_bad_credentials_rejected(anon_client) :
    import auth
    auth.create_user("a@home", "rightpass", role="admin", household_id=1)
    assert anon_client.post("/auth/login", json={"email": "a@home", "password": "nope"}).status_code == 401
    assert anon_client.post("/auth/login", json={"email": "ghost@home", "password": "x"}).status_code == 401


def test_login_me_logout(client) :
    me = client.get("/auth/me").json()
    assert me["email"] == "test@home" and me["role"] == "admin" and me["household_id"] == 1
    assert client.post("/auth/logout").status_code == 200
    # session invalidated
    assert client.get("/foods").status_code == 401


# --- multi-tenant isolation ------------------------------------------------

def test_two_households_are_isolated() :
    h1 = make_client("one@home", "pw123456", role="admin", household_id=1)
    h2 = make_client("two@home", "pw123456", role="admin", household_id=2)

    h1.post("/foods", json={"name": "eggs"})
    h1.post("/inventory/add", json={"name": "eggs", "amount": 5})
    h1.post("/spending", json={"name": "eggs", "qty": 1, "unit_cost": 4.0})

    h2.post("/foods", json={"name": "milk"})
    h2.post("/inventory/add", json={"name": "milk", "amount": 2})

    # each household sees only its own catalog / inventory / spending
    assert [f["name"] for f in h1.get("/foods").json()] == ["eggs"]
    assert [f["name"] for f in h2.get("/foods").json()] == ["milk"]
    assert h1.get("/inventory").json()["foods"] == {"eggs": 5}
    assert h2.get("/inventory").json()["foods"] == {"milk": 2}
    assert len(h1.get("/spending").json()) == 1
    assert h2.get("/spending").json() == []

    # spending ids are per-household: both start at 1 without colliding
    assert h2.post("/spending", json={"name": "milk", "qty": 1, "unit_cost": 2.0}).json()["id"] == 1


# --- admin gate ------------------------------------------------------------

def test_only_admin_can_create_users() :
    member = make_client("m@home", "pw123456", role="member", household_id=1)
    assert member.post("/auth/users", json={"email": "x@home", "password": "pw123456"}).status_code == 403

    admin = make_client("adm@home", "pw123456", role="admin", household_id=1)
    assert admin.post("/auth/users", json={"email": "kid@home", "password": "pw123456"}).status_code == 200
    emails = {u["email"] for u in admin.get("/auth/users").json()}
    assert {"m@home", "adm@home", "kid@home"} <= emails
