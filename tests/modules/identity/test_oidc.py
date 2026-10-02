"""ADC-008 §Bảo mật — xác minh ID token, PKCE, chặn open redirect."""

import time

import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

from src.modules.identity.oidc import (
    AuthError,
    AuthErrorCode,
    is_domain_allowed,
    pkce_challenge,
    safe_next_path,
    verify_id_token,
)
from tests.google_fake import CLIENT_ID, FakeGoogle

CLAIMS = {"sub": "s1", "email": "An@ADC.test", "email_verified": True, "name": "An", "nonce": "n1"}


@pytest.fixture(scope="module")
def google():
    return FakeGoogle()


def verify(google, token, nonce="n1"):
    return verify_id_token(token, google.jwks(), client_id=CLIENT_ID, nonce=nonce)


def test_valid_token_returns_identity_with_lowercased_email(google):
    identity = verify(google, google.sign(CLAIMS))
    assert (identity.sub, identity.email, identity.email_verified) == ("s1", "an@adc.test", True)


@pytest.mark.parametrize(
    "override",
    [
        {"aud": "other-client"},
        {"iss": "https://evil.example"},
        {"exp": int(time.time()) - 3600},
        {"nonce": "replayed"},
    ],
)
def test_rejects_wrong_aud_iss_exp_nonce(google, override):
    with pytest.raises(AuthError) as e:
        verify(google, google.sign({**CLAIMS, **override}))
    assert e.value.code == AuthErrorCode.AUTH_FAILED


def test_rejects_token_signed_by_other_key(google):
    forged = google.sign(CLAIMS, key=rsa.generate_private_key(public_exponent=65537, key_size=2048))
    with pytest.raises(AuthError):
        verify(google, forged)


def test_rejects_unknown_kid(google):
    with pytest.raises(AuthError):
        verify(google, google.sign(CLAIMS, kid="rotated"))


def test_email_verified_must_be_true_boolean(google):
    assert not verify(google, google.sign({**CLAIMS, "email_verified": "true"})).email_verified


def test_pkce_s256_rfc7636_example():
    assert (
        pkce_challenge("dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk") == "E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM"
    )


def test_domain_allowlist_is_fail_closed():
    assert is_domain_allowed("a@ADC.test", {"adc.test"})
    assert not is_domain_allowed("a@gmail.com", {"adc.test"})
    assert not is_domain_allowed("a@adc.test", set())


@pytest.mark.parametrize("bad", [None, "", "https://evil.com", "//evil.com", "/\\evil.com", "board"])
def test_next_path_blocks_open_redirect(bad):
    assert safe_next_path(bad) is None


def test_next_path_keeps_relative_path():
    assert safe_next_path("/board?line=A") == "/board?line=A"
