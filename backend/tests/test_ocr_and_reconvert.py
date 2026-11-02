import shutil

import pytest
from fastapi.testclient import TestClient
from PIL import Image, ImageDraw, ImageFont

from app import ocr
from app.config import Settings
from app.main import create_app
from tests.pdfgen import make_pdf
from tests.test_library import GOOD_PDF_LINES, fake_ocr, up

SCAN = make_pdf([[""], [""]])        # a PDF with no text layer, like a scan


def client_for(tmp_path, **options):
    app = create_app(Settings(data_dir=tmp_path, request_delay_s=0), start_scheduler=False, library_lookups=False,
                     library_options={"sync_jobs": True, **options})
    c = TestClient(app, headers={"X-Requested-With": "aec"})
    c.__enter__()
    assert c.post("/api/setup", json={"username": "admin", "password": "correct horse battery"}).status_code == 200
    c.data_dir = tmp_path
    return c


def test_scanned_pdf_is_read_automatically(tmp_path):
    c = client_for(tmp_path, ocr_function=fake_ocr)
    r = up(c, "scan.pdf", SCAN).json()
    item = c.get(f"/api/library/{r['id']}").json()
    assert item["status"] == "converted" and item["ocr"] is True and item["ocr_confidence"] == 91
    assert "OCR" in item["converter"] and "check any number" in item["message"] and "Low-confidence pages: 2" in item["message"]
    assert "Recognised words about training load" in item["fulltext"]
    assert c.get("/api/library", params={"q": "recognised"}).json()["items"][0]["id"] == r["id"]


def test_picture_files_are_read_too(tmp_path):
    import io
    buf = io.BytesIO()
    Image.new("RGB", (50, 50), "white").save(buf, "PNG")
    c = client_for(tmp_path, ocr_function=fake_ocr)
    r = up(c, "screenshot-of-a-table.png", buf.getvalue()).json()
    assert c.get(f"/api/library/{r['id']}").json()["status"] == "converted"


def test_progress_is_reported_while_reading(tmp_path):
    seen = {}

    def watching_ocr(data, filename, *, langs="eng", progress=None):
        progress(1, 3)
        seen["during"] = dict(lib.progress)
        return fake_ocr(data, filename, progress=progress)

    c = client_for(tmp_path, ocr_function=watching_ocr)
    lib = c.app.state.library
    r = up(c, "scan.pdf", SCAN).json()
    assert seen["during"][r["id"]] == {"done": 1, "total": 3} and lib.progress == {}


def test_without_ocr_the_scan_is_kept_and_says_so(tmp_path, monkeypatch):
    monkeypatch.setattr(ocr, "available", lambda: False)
    c = client_for(tmp_path)
    r = up(c, "scan.pdf", SCAN).json()
    item = c.get(f"/api/library/{r['id']}").json()
    assert item["status"] == "needs_ocr" and "not available" in item["message"] and item["has_source"]
    assert c.post(f"/api/library/{r['id']}/ocr").status_code == 400


def test_ocr_that_finds_nothing_is_not_retried_until_you_ask(tmp_path):
    def empty(data, filename, *, langs="eng", progress=None):
        return ocr.OcrResult(markdown="", pages=2, chars=3, engine="tesseract test")

    c = client_for(tmp_path, ocr_function=empty)
    r = up(c, "blank.pdf", SCAN).json()
    item = c.get(f"/api/library/{r['id']}").json()
    assert item["status"] == "needs_ocr" and item["ocr_tried"] is True and "almost no readable text" in item["message"]
    c.post("/api/library/rescan")
    assert c.get(f"/api/library/{r['id']}").json()["status"] == "needs_ocr"       # no loop on every scan
    c.app.state.library.ocr_function = fake_ocr                                       # e.g. after a better engine arrives
    assert c.post(f"/api/library/{r['id']}/ocr").status_code == 200
    assert c.get(f"/api/library/{r['id']}").json()["status"] == "converted"


def test_ocr_engine_error_is_reported_cleanly(tmp_path):
    def broken(data, filename, *, langs="eng", progress=None):
        raise ocr.OcrError("Tesseract failed on page 1 (RuntimeError).")

    c = client_for(tmp_path, ocr_function=broken)
    r = up(c, "scan.pdf", SCAN).json()
    item = c.get(f"/api/library/{r['id']}").json()
    assert item["status"] == "needs_ocr" and "Tesseract failed on page 1" in item["message"]


def test_scans_stored_by_an_older_version_are_read_after_upgrade(tmp_path):
    c = client_for(tmp_path, ocr_function=None)            # first the install has no OCR
    c.app.state.library.ocr_function = None
    root = tmp_path / "ingest"
    import app.ocr as o
    orig = o.available
    o.available = lambda: False
    try:
        r = up(c, "old-scan.pdf", SCAN).json()
        assert c.get(f"/api/library/{r['id']}").json()["status"] == "needs_ocr"
    finally:
        o.available = orig
    c.app.state.library.ocr_function = fake_ocr             # now the upgraded image has OCR; the next scan picks the item up
    c.post("/api/library/rescan")
    assert c.get(f"/api/library/{r['id']}").json()["status"] == "converted" and (root / "3-source" / f"{r['id']}.pdf").exists()


def test_interrupted_ocr_resumes_after_a_restart(tmp_path):
    c = client_for(tmp_path, ocr_function=fake_ocr)
    r = up(c, "scan.pdf", SCAN).json()
    lib = c.app.state.library
    lib._set_fields(r["id"], {"status": "ocr_pending"})       # as if the server stopped mid-way
    c.post("/api/library/rescan")
    assert c.get(f"/api/library/{r['id']}").json()["status"] == "converted"


def test_existing_conversions_are_redone_when_the_converter_improves(tmp_path):
    c = client_for(tmp_path)
    r = up(c, "paper.pdf", make_pdf([GOOD_PDF_LINES])).json()
    c.patch(f"/api/library/{r['id']}", json={"tags": "mine", "notes": "my note", "reviewed": True})
    path = tmp_path / "ingest" / "2-fulltext" / f"{r['id']}.md"
    text = path.read_text().replace('conv_ver: 2', 'conv_ver: 1')
    path.write_text(text.replace("Heart rate variability", "Heart rate vari -\nability"))           # an old, uglier conversion
    assert "vari -" in path.read_text()
    c.post("/api/library/rescan")
    item = c.get(f"/api/library/{r['id']}").json()
    assert "vari -" not in item["fulltext"] and "Heart rate variability" in item["fulltext"]
    assert item["tags"] == ["mine"] and item["notes"] == "my note" and item["reviewed"] is True       # what you wrote survives
    assert item["conv_ver"] == 2
    before = path.read_text()
    c.post("/api/library/rescan")
    assert path.read_text() == before                                                                  # and it is not redone every scan


def test_status_counts_include_the_new_state(tmp_path):
    c = client_for(tmp_path, ocr_function=fake_ocr)
    assert "ocr_pending" in c.get("/api/library").json()["statuses"]


# ---- the real engine (skipped where Tesseract is not installed) -----------------------------------------------------
@pytest.mark.skipif(shutil.which("tesseract") is None, reason="Tesseract is not installed")
def test_real_tesseract_reads_an_image_only_pdf(tmp_path):
    font = ImageFont.load_default(size=46)
    img = Image.new("RGB", (1700, 700), "white")
    d = ImageDraw.Draw(img)
    for i, line in enumerate(["Heart rate variability was measured every morning",
                              "in twelve trained runners over eight weeks.", "", "Athletes who raised weekly distance gradually",
                              "showed stable values."]):
        d.text((80, 60 + i * 90), line, fill="black", font=font)
    pdf = tmp_path / "scan.pdf"
    img.save(pdf, "PDF", resolution=200)
    res = ocr.ocr_document(pdf.read_bytes(), "scan.pdf")
    assert "variability" in res.markdown.lower() and "runners" in res.markdown.lower() and res.pages == 1
    assert res.confidence and res.confidence > 60
    assert convert_has_no_text(pdf.read_bytes())


def convert_has_no_text(data):
    from app import convert
    return convert.pdf_to_markdown(data).status == "needs_ocr"
