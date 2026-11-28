"""AI-assisted partial evaluator draft derived from w-102's public request/code.

NOT EXECUTED on a research method artifact. Only fake credentials and reserved
.invalid names are used; the tests never send a request. Bind imported Requests
and dependencies to the final artifact in an isolated evaluator. Passing does
not establish Python 3.8.12 equivalence or a real HTTP-407 proxy reproduction.
"""
import base64

import pytest
from requests.adapters import HTTPAdapter
from requests.utils import get_auth_from_url, prepend_scheme_if_needed


@pytest.mark.parametrize("proxy,scheme", [
    ("reviewer:fixture-password@proxy.example.invalid:3128", "http"),
    ("http://reviewer:fixture-password@proxy.example.invalid:3128", "http"),
    ("https://reviewer:fixture-password@proxy.example.invalid:3128", "http"),
])
def test_proxy_credentials_survive_normalization_and_header_generation(proxy, scheme):
    normalized = prepend_scheme_if_needed(proxy, scheme)
    assert get_auth_from_url(normalized) == ("reviewer", "fixture-password")
    headers = HTTPAdapter().proxy_headers(normalized)
    expected = "Basic " + base64.b64encode(b"reviewer:fixture-password").decode("ascii")
    assert headers.get("Proxy-Authorization") == expected
    if proxy.startswith("https://"):
        assert normalized.startswith("https://")


def test_encoded_authentication_preserves_decoded_credentials():
    normalized = prepend_scheme_if_needed("name%40example:p%3Ass@proxy.example.invalid:3128", "http")
    assert get_auth_from_url(normalized) == ("name@example", "p:ss")
    expected = "Basic " + base64.b64encode(b"name@example:p:ss").decode("ascii")
    assert HTTPAdapter().proxy_headers(normalized).get("Proxy-Authorization") == expected


@pytest.mark.parametrize("proxy", ["proxy.example.invalid:3128", "http://proxy.example.invalid:3128"])
def test_proxy_without_credentials_does_not_gain_authentication(proxy):
    normalized = prepend_scheme_if_needed(proxy, "http")
    assert get_auth_from_url(normalized) == ("", "")
    assert "Proxy-Authorization" not in HTTPAdapter().proxy_headers(normalized)
