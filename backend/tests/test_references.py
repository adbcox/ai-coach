import re
from pathlib import Path

from app import maxhr, references, vo2max


def test_every_cited_id_exists_and_is_complete():
    for r in references.all_references():
        assert r["title"] and r["authors"] and r["used_for"] and r["how_used"] and r["limits"] and r["verified_note"]
        assert r["verified"] in references.VERIFIED
    ids = {r["id"] for r in references.REFERENCES}
    assert len(ids) == len(references.REFERENCES)  # unique
    for module in (vo2max, maxhr):
        pass
    for cid in vo2max.CITATION_IDS:
        assert cid in ids


def test_no_unverified_publication_details_are_invented():
    # details we could not verify are left out rather than guessed
    uth = next(r for r in references.all_references() if r["id"] == "uth2004")
    assert uth["doi"] is None and "91" not in uth["venue"]
    assert next(r for r in references.all_references() if r["id"] == "minetti2002")["verified"] == "full_text"


def test_docs_references_file_is_in_sync_with_the_code():
    doc = Path(__file__).resolve().parents[2] / "docs" / "references.md"
    assert doc.read_text().strip() == references.to_markdown().strip(), (
        "docs/references.md is out of date: run `python -m app.references > ../docs/references.md` in backend/")


def test_api_methods_name_known_sources_and_zone_wording_is_honest(authed):
    ids = {r["id"] for r in references.REFERENCES}
    data = authed.get("/api/predictions").json()
    for t in data["targets"]:
        for m in t["methods"]:
            assert m["citation"] in ids, m
    assert data["gap_model"]["citation"] in ids
    prefs = authed.get("/api/preferences").json()
    assert "common five-zone convention" in prefs["hr_zone_note"] and "Garmin's default" not in prefs["hr_zone_note"]
    assert prefs["hr_zone_citation"] in ids
    refs = authed.get("/api/references").json()
    assert refs["verified_levels"] and len(refs["references"]) == len(ids)
    assert all(re.match(r"^[a-z0-9_]+$", r["id"]) for r in refs["references"])
