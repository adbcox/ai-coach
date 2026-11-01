
import httpx
import pytest
from fastapi.testclient import TestClient

from app import convert, fetch, library
from app.config import Settings
from app.main import create_app
from tests.pdfgen import make_pdf

PARAGRAPH = ("Heart rate variability was measured every morning in twelve trained runners over eight weeks. "
             "The athletes who increased their weekly distance gradually showed stable values, while a sudden jump "
             "in training load was followed by a drop. These findings apply to trained recreational runners only. ") * 3
GOOD_PDF_LINES = ["Effects of Gradual Training Load on Heart Rate Variability", "J. Smith and A. Jones", "Published 2024",
                  "doi: 10.1234/abcd.2024.001"] + [PARAGRAPH[i:i + 90] for i in range(0, len(PARAGRAPH), 90)]

CROSSREF = {"message": {"title": ["Effects of Gradual Training Load on Heart Rate Variability"], "DOI": "10.1234/ABCD.2024.001",
                        "author": [{"given": "Jane", "family": "Smith"}, {"given": "Alan", "family": "Jones"}],
                        "issued": {"date-parts": [[2024, 3]]}, "container-title": ["Journal of Test Physiology"],
                        "URL": "https://doi.org/10.1234/abcd.2024.001", "type": "journal-article"}}

HTML_PAGE = ("<html><head><title>Polarized training explained</title><meta name='author' content='Pat Coach'></head><body>"
             "<nav>menu menu menu</nav><article><h1>Polarized training explained</h1>"
             + "".join(f"<p>{PARAGRAPH}</p>" for _ in range(2)) + "</article><footer>cookies</footer></body></html>")


def handler(request: httpx.Request) -> httpx.Response:
    url = str(request.url)
    if url.startswith("https://api.crossref.org/works/10.1234"):
        return httpx.Response(200, json=CROSSREF)
    if url.startswith("https://api.crossref.org/"):
        return httpx.Response(404)
    if url == "https://example.org/article":
        return httpx.Response(200, text=HTML_PAGE, headers={"content-type": "text/html; charset=utf-8"})
    if url == "https://example.org/paper.pdf":
        return httpx.Response(200, content=make_pdf([GOOD_PDF_LINES]), headers={"content-type": "application/pdf"})
    if url == "https://example.org/redirect":
        return httpx.Response(302, headers={"location": "http://10.0.0.5/secret"})
    if url == "https://example.org/blocked":
        return httpx.Response(403)
    return httpx.Response(404)


def public_resolver(host: str) -> list[str]:
    return {"internal.example": ["10.1.2.3"], "loop.example": ["127.0.0.1"]}.get(host, ["93.184.216.34"])


@pytest.fixture
def lib_client(tmp_path):
    settings = Settings(data_dir=tmp_path, request_delay_s=0)
    app = create_app(settings, start_scheduler=False, library_transport=httpx.MockTransport(handler),
                     library_resolver=public_resolver)
    with TestClient(app, headers={"X-Requested-With": "aec"}) as c:
        assert c.post("/api/setup", json={"username": "admin", "password": "correct horse battery"}).status_code == 200
        c.data_dir = tmp_path
        yield c


def up(c, name, data, **params):
    return c.put("/api/library/upload", params={"filename": name, **params}, content=data)


# ----------------------------------------------------------------------------- converters
def test_front_matter_round_trip_and_hand_written_yaml():
    meta = {"id": "x", "title": 'A "quoted": title', "authors": ["A B", "C D"], "year": 2024, "reviewed": False,
            "tags": ["hrv", "recovery"], "words": 0, "notes": None}
    text = library.dump_front_matter(meta) + "\nbody here\n"
    back, body = library.parse_front_matter(text)
    assert back["title"] == 'A "quoted": title' and back["authors"] == ["A B", "C D"] and back["year"] == 2024
    assert back["reviewed"] is False and back["words"] == 0 and "notes" not in back and body.strip() == "body here"
    hand, _ = library.parse_front_matter("---\ntitle: Plain title\ntags: [a, b]\nauthors:\n  - One\n  - Two\nyear: 2020\n---\nx")
    assert hand == {"title": "Plain title", "tags": ["a", "b"], "authors": ["One", "Two"], "year": 2020}


def test_doi_helpers():
    assert convert.find_doi("see https://doi.org/10.1000/xyz123.") == "10.1000/xyz123"
    assert convert.clean_doi("doi: 10.1000/ABC") == "10.1000/abc"
    assert convert.find_doi("nothing here") is None


def test_pdf_text_extraction_and_metadata():
    c = convert.pdf_to_markdown(make_pdf([GOOD_PDF_LINES, ["Second page text " * 20]], title="Effects of Gradual Training Load"))
    assert c.status == "converted" and c.pages == 2 and "page 2" in c.markdown
    assert "Heart rate variability" in c.markdown and c.doi == "10.1234/abcd.2024.001" and c.title.startswith("Effects")
    assert c.year == 2024


def test_scanned_pdf_is_flagged_not_converted():
    c = convert.pdf_to_markdown(make_pdf([[""], [""]]))
    assert c.status == "needs_ocr" and "OCR" in c.message


def test_garbage_pdf_fails_cleanly():
    assert convert.pdf_to_markdown(b"%PDF-1.4 not really").status == "failed"


def test_html_and_text_conversion():
    c = convert.html_to_markdown(HTML_PAGE, "https://example.org/article")
    assert c.status == "converted" and "Heart rate variability" in c.markdown and "menu menu" not in c.markdown
    assert convert.html_to_markdown("<html><body><p>tiny</p></body></html>").status == "failed"
    t = convert.text_to_markdown(b"# My Notes\n\ntext 10.1000/abc.1", markdown=True)
    assert t.title == "My Notes" and t.doi == "10.1000/abc.1"
    assert convert.convert("x.docx", b"PK")[1] == ""


# ----------------------------------------------------------------------------- safe fetching
@pytest.mark.parametrize("url", ["ftp://example.org/x", "http://localhost/x", "http://127.0.0.1/x", "http://10.0.0.1/",
                                 "http://192.168.1.5/", "http://169.254.169.254/latest", "http://[::1]/", "http://internal.example/",
                                 "http://loop.example/", "file:///etc/passwd", "http://nas.local/"])
def test_private_addresses_are_refused(url):
    with pytest.raises(fetch.FetchError):
        fetch.check_public_url(url, public_resolver)


def test_public_address_is_allowed_and_redirect_to_private_is_refused():
    assert fetch.check_public_url("https://example.org/a", public_resolver).startswith("https://")
    with pytest.raises(fetch.FetchError):
        fetch.fetch("https://example.org/redirect", transport=httpx.MockTransport(handler), resolve=public_resolver)
    with pytest.raises(fetch.FetchError):
        fetch.fetch("https://example.org/blocked", transport=httpx.MockTransport(handler), resolve=public_resolver)


def test_size_cap():
    big = httpx.MockTransport(lambda r: httpx.Response(200, content=b"x" * 5000, headers={"content-type": "text/html"}))
    with pytest.raises(fetch.FetchError):
        fetch.fetch("https://example.org/", transport=big, resolve=public_resolver, max_bytes=1000)


def test_crossref_record():
    rec = fetch.crossref_record("10.1234/abcd.2024.001", transport=httpx.MockTransport(handler))
    assert rec["title"].startswith("Effects") and rec["authors"] == ["Jane Smith", "Alan Jones"] and rec["year"] == 2024
    assert fetch.crossref_record("10.9999/none", transport=httpx.MockTransport(handler)) is None


# ----------------------------------------------------------------------------- the API
def test_requires_login(tmp_path):
    app = create_app(Settings(data_dir=tmp_path, request_delay_s=0), start_scheduler=False)
    with TestClient(app, headers={"X-Requested-With": "aec"}) as c:
        assert c.get("/api/library").status_code == 401
        assert c.put("/api/library/upload", params={"filename": "a.pdf"}, content=b"x").status_code == 401


def test_upload_pdf_converts_enriches_and_writes_three_tiers(lib_client):
    c = lib_client
    r = up(c, "download (3).pdf", make_pdf([GOOD_PDF_LINES])).json()
    assert r["status"] == "converted" and r["duplicate"] is False
    assert r["title"].startswith("Effects of Gradual") and r["authors"] == ["Jane Smith", "Alan Jones"]  # from Crossref
    assert r["year"] == 2024 and r["doi"] == "10.1234/abcd.2024.001" and r["id"].startswith("smith-2024-")
    root = c.data_dir / "ingest"
    assert (root / "3-source" / f"{r['id']}.pdf").read_bytes()[:5] == b"%PDF-"
    text = (root / "2-fulltext" / f"{r['id']}.md").read_text()
    assert text.startswith("---") and "Heart rate variability" in text and "pypdf" in text
    assert "Effects of Gradual" in (root / "INDEX.md").read_text()
    item = c.get(f"/api/library/{r['id']}").json()
    assert "Heart rate variability" in item["fulltext"] and item["has_source"] and item["source_ext"] == ".pdf"
    assert c.get(f"/api/library/{r['id']}/source").content[:5] == b"%PDF-"


def test_duplicate_upload_is_detected(lib_client):
    data = make_pdf([GOOD_PDF_LINES])
    first = up(lib_client, "a.pdf", data).json()
    again = up(lib_client, "b.pdf", data).json()
    assert again["duplicate"] is True and again["id"] == first["id"]
    assert lib_client.get("/api/library").json()["total"] == 1


def test_scanned_and_unsupported_files(lib_client):
    r = up(lib_client, "scan.pdf", make_pdf([[""]])).json()
    assert r["status"] == "needs_ocr"
    bad = up(lib_client, "photo.jpg", b"\xff\xd8\xff")
    assert bad.status_code == 400 and "not supported" in bad.json()["detail"]
    assert up(lib_client, "empty.txt", b"").status_code == 400


def test_markdown_and_text_upload(lib_client):
    r = up(lib_client, "my-notes.md", b"# Coach notes on tapering\n\nReduce volume by 40% in the last two weeks.").json()
    assert r["title"] == "Coach notes on tapering" and r["status"] == "converted"
    assert lib_client.get("/api/library", params={"q": "tapering"}).json()["items"][0]["id"] == r["id"]


def test_link_to_article_pdf_and_blocked_hosts(lib_client):
    page = lib_client.post("/api/library/link", json={"url": "https://example.org/article"}).json()
    assert page["status"] == "converted" and page["url"] == "https://example.org/article"
    pdf = lib_client.post("/api/library/link", json={"url": "https://example.org/paper.pdf"}).json()
    assert pdf["status"] == "converted" and pdf["doi"] == "10.1234/abcd.2024.001"
    for bad in ("http://127.0.0.1:26219/api/health", "http://internal.example/x", "https://example.org/redirect", "notaurl"):
        r = lib_client.post("/api/library/link", json={"url": bad})
        assert r.status_code == 400, bad
    assert lib_client.post("/api/library/link", json={"url": "https://example.org/blocked"}).status_code == 400


def test_doi_and_manual_citation(lib_client):
    r = lib_client.post("/api/library/link", json={"url": "https://doi.org/10.1234/abcd.2024.001"}).json()
    assert r["status"] == "citation_only" and r["title"].startswith("Effects") and r["authors"][0] == "Jane Smith"
    again = lib_client.post("/api/library/link", json={"url": "doi:10.1234/abcd.2024.001"}).json()
    assert again["duplicate"] is True
    assert lib_client.post("/api/library/link", json={"url": "10.9999/unknown"}).status_code == 400
    m = lib_client.post("/api/library/citation", json={"title": "Daniels' Running Formula", "authors": "Daniels J",
                                                       "year": 2014, "evidence_type": "book"}).json()
    assert m["status"] == "citation_only" and m["id"].startswith("daniels-2014")
    assert lib_client.post("/api/library/citation", json={"title": ""}).status_code == 422


def test_attach_full_text_to_a_citation_and_link_to_a_built_in_source(lib_client):
    cit = lib_client.post("/api/library/citation", json={"title": "Age-predicted maximal heart rate revisited",
                                                         "authors": ["Tanaka H"], "year": 2001, "ref_id": "tanaka2001"}).json()
    refs = {x["id"]: x for x in lib_client.get("/api/references").json()["references"]}
    assert refs["tanaka2001"]["your_copy"]["id"] == cit["id"] and refs["minetti2002"]["your_copy"] is None
    r = lib_client.post(f"/api/library/{cit['id']}/attach", params={"filename": "t.pdf"}, content=make_pdf([GOOD_PDF_LINES]))
    assert r.status_code == 200 and r.json()["status"] == "converted" and r.json()["ref_id"] == "tanaka2001"
    assert r.json()["title"] == "Age-predicted maximal heart rate revisited"  # your details are kept
    assert lib_client.post("/api/library/citation", json={"title": "x", "ref_id": "nope"}).status_code == 400
    assert up(lib_client, "z.md", b"# Z\n\ntext", ref_id="nope").status_code == 400


def test_edit_details_tags_notes_and_search(lib_client):
    a = up(lib_client, "a.md", b"# Tempo runs\n\nLactate threshold work improves half marathon pace.").json()
    b = up(lib_client, "b.md", b"# Sleep and recovery\n\nSleep extension helps athletes recover.").json()
    p = lib_client.patch(f"/api/library/{a['id']}", json={"tags": "threshold, tempo", "reviewed": True, "year": 2020,
                                                          "evidence_type": "review", "authors": "Lee K; Park S",
                                                          "notes": "useful for the half"}).json()
    assert p["tags"] == ["threshold", "tempo"] and p["reviewed"] is True and p["authors"] == ["Lee K", "Park S"]
    assert lib_client.patch(f"/api/library/{a['id']}", json={"evidence_type": "vibes"}).status_code == 400
    assert lib_client.patch(f"/api/library/{a['id']}", json={"title": " "}).status_code == 400
    hit = lib_client.get("/api/library", params={"q": "lactate"}).json()["items"]
    assert [x["id"] for x in hit] == [a["id"]] and "[[" in hit[0]["snippet"]
    assert [x["id"] for x in lib_client.get("/api/library", params={"q": "recover"}).json()["items"]] == [b["id"]]  # stemming
    assert [x["id"] for x in lib_client.get("/api/library", params={"tag": "tempo"}).json()["items"]] == [a["id"]]
    assert [x["id"] for x in lib_client.get("/api/library", params={"reviewed": "1"}).json()["items"]] == [a["id"]]
    assert lib_client.get("/api/library", params={"q": "zzzznothing"}).json()["items"] == []
    assert lib_client.get("/api/library", params={"q": 'half" OR *'}).status_code == 200  # no query injection
    assert lib_client.get("/api/library").json()["tags"] == ["tempo", "threshold"]
    assert lib_client.get("/api/library", params={"q": "useful"}).json()["items"][0]["id"] == a["id"]  # notes are searchable


def test_actionable_notes_file(lib_client):
    a = up(lib_client, "a.md", b"# Paper\n\nSome findings about pacing in marathons here.").json()
    item = lib_client.get(f"/api/library/{a['id']}").json()
    assert item["actionable"]["exists"] is False
    r = lib_client.put(f"/api/library/{a['id']}/actionable", json={"body": "## Items\n1. **Claim/action:** negative splits", "status": "draft"})
    assert r.status_code == 200 and r.json()["status"] == "draft"
    path = lib_client.data_dir / "ingest" / "1-actionable" / f"{a['id']}.md"
    assert "negative splits" in path.read_text() and path.read_text().startswith("---")
    done = lib_client.put(f"/api/library/{a['id']}/actionable", json={"body": "negative splits, reviewed", "status": "reviewed"}).json()
    assert done["status"] == "reviewed" and done["reviewed_on"]
    assert lib_client.get("/api/library", params={"q": "splits"}).json()["items"][0]["id"] == a["id"]
    assert lib_client.put(f"/api/library/{a['id']}/actionable", json={"body": "x", "status": "weird"}).status_code == 400


def test_files_are_the_source_of_truth_rescan_and_inbox(lib_client):
    root = lib_client.data_dir / "ingest"
    (root / "2-fulltext" / "my-hand-written.md").write_text("# Hand written note\n\nPacing is a skill you can practise often.\n")
    (root / "inbox" / "dropped paper.pdf").write_bytes(make_pdf([GOOD_PDF_LINES]))
    (root / "inbox" / "photo.jpg").write_bytes(b"\xff\xd8\xff")
    r = lib_client.post("/api/library/rescan").json()
    assert r["converted"] >= 1
    items = {x["id"]: x for x in lib_client.get("/api/library").json()["items"]}
    assert "my-hand-written" in items and items["my-hand-written"]["title"] == "Hand written note"
    assert any(i.startswith("smith-2024") for i in items)
    assert not (root / "inbox" / "dropped paper.pdf").exists() and (root / "inbox" / "photo.jpg.rejected").exists()
    assert "photo.jpg.error.txt" in [p.name for p in (root / "inbox").iterdir()]
    (root / "2-fulltext" / "my-hand-written.md").unlink()
    lib_client.post("/api/library/rescan")
    assert "my-hand-written" not in {x["id"] for x in lib_client.get("/api/library").json()["items"]}


def test_reconvert_keeps_what_you_wrote(lib_client):
    r = up(lib_client, "a.pdf", make_pdf([GOOD_PDF_LINES])).json()
    lib_client.patch(f"/api/library/{r['id']}", json={"tags": "keep-me", "notes": "mine", "title": "My own title"})
    out = lib_client.post(f"/api/library/{r['id']}/reconvert").json()
    assert out["tags"] == ["keep-me"] and out["notes"] == "mine" and out["title"] == "My own title" and out["status"] == "converted"


def test_delete_removes_all_tiers(lib_client):
    r = up(lib_client, "a.pdf", make_pdf([GOOD_PDF_LINES])).json()
    lib_client.put(f"/api/library/{r['id']}/actionable", json={"body": "x", "status": "draft"})
    assert lib_client.delete(f"/api/library/{r['id']}").status_code == 200
    root = lib_client.data_dir / "ingest"
    assert not list(root.glob(f"*/{r['id']}.*")) and lib_client.get(f"/api/library/{r['id']}").status_code == 404
    assert lib_client.get("/api/library").json()["total"] == 0


def test_ids_cannot_escape_the_library_folder(lib_client):
    for bad in ("..%2F..%2Fetc%2Fpasswd", "..", "a%2Fb", "UPPER"):
        assert lib_client.get(f"/api/library/{bad}").status_code in (404, 405)
        assert lib_client.get(f"/api/library/{bad}/source").status_code in (404, 405)
        assert lib_client.delete(f"/api/library/{bad}").status_code in (400, 404, 405)


def test_library_is_included_in_backups_and_never_in_git():
    import pathlib
    ignore = (pathlib.Path(__file__).parents[2] / ".gitignore").read_text()
    assert "*.pdf" in ignore and "data/" in ignore


def test_library_survives_backup_and_restore_and_is_reindexed(tmp_path):
    from tests.test_backup import make_client, wait_backup
    a, _ = make_client(tmp_path / "a")
    with a:
        a.post("/api/setup", json={"username": "admin", "password": "correct horse battery"})
        item = up(a, "keep.md", b"# A paper I want to keep\n\nSome text about pacing strategy for marathons.").json()
        a.put(f"/api/library/{item['id']}/actionable", json={"body": "my own note about negative splits", "status": "draft"})
        a.post("/api/backups", json={})
        data = a.get("/api/backups/" + wait_backup(a)["items"][0]["name"]).content
    b, _ = make_client(tmp_path / "b")
    with b:
        assert b.put("/api/restore", content=data).status_code == 200
        assert b.post("/api/login", json={"username": "admin", "password": "correct horse battery"}).status_code == 200
        got = b.get(f"/api/library/{item['id']}").json()
        assert got["title"] == "A paper I want to keep" and got["actionable"]["body"].startswith("my own note")
        assert [x["id"] for x in b.get("/api/library", params={"q": "negative splits"}).json()["items"]] == [item["id"]]
