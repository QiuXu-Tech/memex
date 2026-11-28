"""AI-assisted partial oracle v2, developed on independent reference sources.

This version requires explicit HTTP/HTTPS schemes for ordinary credentials.
The original six-case draft and its one failing official-fixed case are retained
as an unresolved exploratory input-format extension, not relabelled as success.
No research method output was read. These tests do not reproduce HTTP 407 or
claim Python 3.8.12 equivalence; they make no network requests.
"""
import base64

import pytest
from requests.adapters import HTTPAdapter
from requests.utils import get_auth_from_url, prepend_scheme_if_needed


@pytest.mark.parametrize("proxy,scheme", [
    ("http://reviewer:fixture-password@proxy.example.invalid:3128", "http"),
    ("https://reviewer:fixture-password@proxy.example.invalid:3128", "http"),
])
def test_proxy_credentials_survive_normalization_and_header_generation(proxy, scheme):
    normalized = prepend_scheme_if_needed(proxy, scheme)
    assert get_auth_from_url(normalized) == ("reviewer", "fixture-password")
    expected = "Basic " + base64.b64encode(b"reviewer:fixture-password").decode("ascii")
    assert HTTPAdapter().proxy_headers(normalized).get("Proxy-Authorization") == expected
    if proxy.startswith("https://"):
        assert normalized.startswith("https://")


def test_encoded_authentication_preserves_decoded_credentials():
    normalized = prepend_scheme_if_needed("http://name%40example:p%3Ass@proxy.example.invalid:3128", "http")
    assert get_auth_from_url(normalized) == ("name@example", "p:ss")
    expected = "Basic " + base64.b64encode(b"name@example:p:ss").decode("ascii")
    assert HTTPAdapter().proxy_headers(normalized).get("Proxy-Authorization") == expected


@pytest.mark.parametrize("proxy", ["proxy.example.invalid:3128", "http://proxy.example.invalid:3128"])
def test_proxy_without_credentials_does_not_gain_authentication(proxy):
    normalized = prepend_scheme_if_needed(proxy, "http")
    assert get_auth_from_url(normalized) == ("", "")
    assert "Proxy-Authorization" not in HTTPAdapter().proxy_headers(normalized)
