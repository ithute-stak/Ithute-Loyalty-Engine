import pytest
from fastapi import HTTPException

from loyalty_api.oidc import decode_access_token


def test_oidc_fail_closed_when_not_configured(monkeypatch):
    from loyalty_api import oidc
    monkeypatch.setattr(oidc.settings, "oidc_issuer", "")
    with pytest.raises(HTTPException) as error:
        decode_access_token("untrusted")
    assert error.value.status_code == 503
