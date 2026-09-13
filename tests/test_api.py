def test_list_leads_basic(client):
    resp = client.get("/leads")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] > 2000  # seed file has ~2049 rows
    assert len(data["leads"]) == 50  # default limit


def test_list_leads_filter_status_case_insensitive(client):
    # seed data has "New", "new", "NEW", " New" - all should normalize to "New"
    resp = client.get("/leads", params={"status": "New", "limit": 500})
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] > 0
    for lead in data["leads"]:
        assert lead["status"] == "New"


def test_list_leads_free_text_search(client):
    resp = client.get("/leads", params={"q": "singh logistics"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] >= 1
    assert any("Singh Logistics" in (l["company_name"] or "") for l in data["leads"])


def test_get_lead_detail_and_404(client):
    resp = client.get("/leads", params={"limit": 1})
    lead_id = resp.json()["leads"][0]["id"]
    detail = client.get(f"/leads/{lead_id}")
    assert detail.status_code == 200
    assert detail.json()["id"] == lead_id

    missing = client.get("/leads/999999")
    assert missing.status_code == 404


def test_patch_lead_updates_status_and_notes(client):
    resp = client.get("/leads", params={"limit": 1})
    lead_id = resp.json()["leads"][0]["id"]

    patched = client.patch(f"/leads/{lead_id}", json={"status": "contacted", "notes": "Called, left voicemail."})
    assert patched.status_code == 200
    body = patched.json()
    assert body["status"] == "Contacted"  # normalized casing
    assert body["notes"] == "Called, left voicemail."


def test_export_csv(client):
    resp = client.get("/leads/export", params={"status": "New"})
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/csv")
    assert b"full_name" in resp.content  # header row present


def test_ingest_creates_new_lead(client):
    payload = {
        "name": "Priya Chandran",
        "email": "priya.chandran@newcorp.example",
        "phone": "+1 555 000 1234",
        "company": "NewCorp Example",
        "country": "United States",
        "message": "Found us through organic google search then booked a demo",
    }
    resp = client.post("/leads/ingest", json=payload)
    assert resp.status_code == 200
    body = resp.json()
    assert body["action"] == "created"
    assert body["lead"]["email"] == payload["email"]
    assert body["lead"]["extracted_channel"] in {"Organic Search", "Website"}


def test_ingest_updates_existing_lead_on_email_match(client):
    first = {
        "name": "Test Person",
        "email": "test.person@dupecheck.example",
        "phone": "+1 555 999 8888",
        "company": "DupeCheck Co",
        "message": "Initial contact via website form",
    }
    r1 = client.post("/leads/ingest", json=first)
    assert r1.json()["action"] == "created"
    lead_id = r1.json()["lead"]["id"]

    second = dict(first)
    second["message"] = "Follow-up: referred by a colleague, warm intro"
    r2 = client.post("/leads/ingest", json=second)
    assert r2.status_code == 200
    assert r2.json()["action"] == "updated"
    assert r2.json()["lead"]["id"] == lead_id
    assert "Follow-up" in r2.json()["lead"]["notes"]


def test_dedupe_candidates_endpoint_returns_groups(client):
    resp = client.post("/leads/dedupe-candidates")
    assert resp.status_code == 200
    data = resp.json()
    assert "groups" in data
    assert data["group_count"] >= 1
    # every group should have at least 2 leads and a confidence score
    for group in data["groups"][:5]:
        assert len(group["lead_ids"]) >= 2
        assert 0 <= group["confidence"] <= 1
        assert len(group["reasons"]) >= 1


def test_dashboard_counts_sum_to_total(client):
    resp = client.get("/dashboard")
    assert resp.status_code == 200
    data = resp.json()
    assert sum(data["by_status"].values()) == data["total_leads"]
    assert sum(data["by_source_channel"].values()) == data["total_leads"]
