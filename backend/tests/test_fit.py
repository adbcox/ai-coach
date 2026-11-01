import pytest

from app.fit.parser import FitError, extract_fit, parse_fit
from tests.fitgen import make_fit, make_zip


def test_parse_generated_fit():
    parsed = parse_fit(make_fit(n=5, sport=1))
    assert len(parsed.samples) == 5
    s0 = parsed.samples[0]
    assert abs(s0.lat - 49.28) < 1e-4 and abs(s0.lon + 123.12) < 1e-4
    assert s0.hr == 140 and abs(s0.speed - 3.0) < 1e-6
    assert abs(s0.alt - 100.0) < 0.5
    assert parsed.sport == "running"
    assert parsed.start_time is not None and parsed.start_time.year >= 2025
    assert parsed.distance_m == 1200.0 and parsed.avg_hr == 142


def test_extract_requires_single_fit():
    assert extract_fit(make_zip(make_fit())).startswith(b"\x0e")
    with pytest.raises(FitError):
        extract_fit(b"not a zip")
    with pytest.raises(FitError):
        extract_fit(make_zip(b"x", name="notes.txt"))


def test_corrupt_fit_raises():
    with pytest.raises(FitError):
        parse_fit(b"\x0e\x20\xd0\x07\xff\xff\xff\x7f.FIT" + b"\x00" * 10)
