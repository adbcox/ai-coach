import httpx
import pytest

from app.garmin.client import GarminClient, GarminError
from tests.conftest import API_KEY, FakeGarmin


def make(fake, key=API_KEY):
    return GarminClient(key, "https://example.test", transport=httpx.MockTransport(fake.handler))


def test_bad_key_is_auth_error():
    with pytest.raises(GarminError) as e:
        make(FakeGarmin(), "wrong-key-123456").ensure_token()
    assert e.value.kind == "auth"


def test_search_and_download_and_token_reuse():
    fake = FakeGarmin()
    c = make(fake)
    assert len(c.search_activities()) == 2
    assert c.download_activity("111").startswith(b"PK")
    with pytest.raises(GarminError):
        c.download_activity("../etc/passwd")


def test_repr_never_contains_key():
    assert API_KEY not in repr(make(FakeGarmin()))


def test_network_error_kind():
    def boom(request):
        raise httpx.ConnectError("down")
    c = GarminClient(API_KEY, "https://x.test", transport=httpx.MockTransport(boom))
    with pytest.raises(GarminError) as e:
        c.ensure_token()
    assert e.value.kind == "network"
