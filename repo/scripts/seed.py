"""
Seed script — populates a fresh database with representative fixtures.

Usage:
    cd repo/
    python scripts/seed.py

Idempotent: running twice is safe (ConflictError on duplicate registration is caught).
Users are created via AuthService.register() inside app_context so privileged
roles (Administrator, Group Leader, etc.) are stored correctly.
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app

os.makedirs("data/keys", exist_ok=True)
os.makedirs("data/logs", exist_ok=True)
os.makedirs("data/attachments", exist_ok=True)

# Generate Fernet key if not present
key_path = "data/keys/secret.key"
if not os.path.exists(key_path):
    from cryptography.fernet import Fernet
    with open(key_path, "wb") as kf:
        kf.write(Fernet.generate_key())
    print(f"  Generated Fernet key at {key_path}")

app = create_app(os.environ.get("FLASK_ENV", "development"))


def _post(client, path, json=None, headers=None):
    resp = client.post(path, json=json or {}, headers=headers or {})
    return resp


def seed():
    # Schema is owned by Alembic migrations only — never db.create_all() here,
    # or Docker restarts can end up with tables but no alembic_version row.

    from app.services.auth_service import AuthService
    from app.errors import ConflictError
    from app.models.user import User

    users_spec = [
        ("admin",       "AdminPass1234!",  "Administrator"),
        ("opsmanager",  "OpsPass1234!",    "Operations Manager"),
        ("moderator",   "ModPass1234!",    "Moderator"),
        ("gl_alice",    "AlicePass1234!",  "Group Leader"),
        ("member_bob",  "BobPass1234!",    "Member"),
    ]

    with app.app_context():
        # ----------------------------------------------------------------
        # 1. Users — use AuthService directly so role is stored correctly
        # ----------------------------------------------------------------
        for username, password, role in users_spec:
            try:
                AuthService.register(username, password, role=role)
                print(f"  registered  {username:20s}  ({role})")
            except ConflictError:
                print(f"  exists      {username:20s}  (skipped)")

        # Fetch gl_alice's user_id from DB — no re-register needed
        gl_alice = User.query.filter_by(username="gl_alice").first()
        if gl_alice is None:
            print("ERROR: gl_alice not found in DB after registration", file=sys.stderr)
            sys.exit(1)
        gl_alice_id = str(gl_alice.user_id)

    # ----------------------------------------------------------------
    # HTTP calls (community, products, inventory, content, template)
    # ----------------------------------------------------------------
    def _login(client, username, password):
        resp = _post(client, "/api/v1/auth/login",
                     json={"username": username, "password": password})
        token = resp.json.get("token", "")
        if not token:
            print(f"ERROR: login failed for {username}: {resp.status_code} {resp.json}",
                  file=sys.stderr)
            sys.exit(1)
        return token

    with app.test_client() as client:
        tokens = {}
        for username, password, _ in users_spec:
            tokens[username] = _login(client, username, password)
            print(f"  login  {username:20s}  token={tokens[username][:16]}…")

        admin_h = {"Authorization": f"Bearer {tokens['admin']}"}
        seeded_community_id = None

        # ----------------------------------------------------------------
        # 2. Community
        # ----------------------------------------------------------------
        comm_resp = _post(client, "/api/v1/communities", json={
            "name": "Austin Community",
            "address_line1": "100 Main St",
            "city": "Austin",
            "state": "TX",
            "zip": "78701",
        }, headers=admin_h)
        if comm_resp.status_code == 201:
            community_id = comm_resp.json["community_id"]
            seeded_community_id = community_id
            print(f"  community  {community_id}")

            # Service area
            _post(client, f"/api/v1/communities/{community_id}/service-areas", json={
                "name": "Downtown",
                "address_line1": "200 Congress Ave",
                "city": "Austin", "state": "TX", "zip": "78701",
            }, headers=admin_h)

            # Bind group leader using user_id fetched from DB
            bind_resp = _post(
                client, f"/api/v1/communities/{community_id}/leader-binding",
                json={"user_id": gl_alice_id}, headers=admin_h,
            )
            if bind_resp.status_code not in (201, 409):
                print(f"ERROR: leader-binding failed: {bind_resp.status_code} {bind_resp.json}",
                      file=sys.stderr)
                sys.exit(1)

            # Commission rule
            _post(client, f"/api/v1/communities/{community_id}/commission-rules", json={
                "rate": 8.0, "floor": 2.0, "ceiling": 12.0, "settlement_cycle": "weekly",
            }, headers=admin_h)
        elif comm_resp.status_code != 409:
            print(f"ERROR: community creation failed: {comm_resp.status_code} {comm_resp.json}",
                  file=sys.stderr)
            sys.exit(1)

        # ----------------------------------------------------------------
        # 3. Products
        # ----------------------------------------------------------------
        products = [
            {"sku": "LAPTOP-001", "name": "ProBook 15", "brand": "TechCo",
             "category": "Electronics", "price_usd": 999.99,
             "tags": ["laptop", "pro"], "attributes": [{"key": "ram", "value": "16GB"}]},
            {"sku": "MOUSE-001", "name": "ErgoMouse", "brand": "TechCo",
             "category": "Electronics", "price_usd": 49.99, "tags": ["mouse", "ergonomic"]},
            {"sku": "BOOK-001", "name": "Python Mastery", "brand": "PressHouse",
             "category": "Books", "price_usd": 34.99, "tags": ["python", "programming"]},
        ]
        product_ids = {}
        for p in products:
            resp = _post(client, "/api/v1/products", json=p, headers=admin_h)
            if resp.status_code == 201:
                product_ids[p["sku"]] = resp.json["product_id"]
                print(f"  product  {p['sku']:20s}  id={product_ids[p['sku']][:8]}…")

        # ----------------------------------------------------------------
        # 4. Warehouse + inventory
        # ----------------------------------------------------------------
        wh_payload = {"name": "Austin Main", "location": "Austin, TX"}
        if seeded_community_id:
            wh_payload["community_id"] = seeded_community_id
        wh_resp = _post(client, "/api/v1/warehouses", json=wh_payload, headers=admin_h)
        if wh_resp.status_code == 201:
            wh_id = wh_resp.json["warehouse_id"]
            print(f"  warehouse  {wh_id[:8]}…")

            _post(client, f"/api/v1/warehouses/{wh_id}/bins",
                  json={"bin_code": "A-01", "description": "Aisle 1"},
                  headers=admin_h)

            for sku, pid in product_ids.items():
                _post(client, "/api/v1/inventory/receipts", json={
                    "sku_id": pid, "warehouse_id": wh_id, "quantity": 50, "unit_cost_usd": 10.0,
                }, headers=admin_h)
                print(f"    receipt  {sku}")

        # ----------------------------------------------------------------
        # 5. Content
        # ----------------------------------------------------------------
        art_resp = _post(client, "/api/v1/content", json={
            "type": "article",
            "title": "Getting Started with Austin Community",
            "body": "<p>Welcome to the Austin Community platform.</p>",
            "tags": ["welcome", "getting-started"],
            "categories": ["announcements"],
        }, headers=admin_h)
        if art_resp.status_code == 201:
            cid = art_resp.json["content_id"]
            _post(client, f"/api/v1/content/{cid}/publish", headers=admin_h)
            print(f"  content  {cid[:8]}…  published")

        # ----------------------------------------------------------------
        # 6. Template
        # ----------------------------------------------------------------
        tmpl_resp = _post(client, "/api/v1/templates", json={
            "name": "Product Capture Form",
            "fields": [
                {"name": "product_name", "type": "text",   "required": True},
                {"name": "quantity",     "type": "number",  "required": True},
                {"name": "notes",        "type": "textarea", "required": False},
            ],
        }, headers=admin_h)
        if tmpl_resp.status_code == 201:
            tid = tmpl_resp.json["template_id"]
            _post(client, f"/api/v1/templates/{tid}/publish", headers=admin_h)
            print(f"  template  {tid[:8]}…  published")

        print("\nSeed complete.")


if __name__ == "__main__":
    seed()
