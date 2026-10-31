from datetime import datetime, timezone

import pytest

from loyalty_api.invitations import (
    create_invitation_token, hash_invitation_token, invitation_expires_at,
    validate_invitation_role,
)


def test_invitation_secrets_are_random_and_hashed():
    first, digest = create_invitation_token()
    second, other_digest = create_invitation_token()
    assert first != second
    assert digest != other_digest
    assert digest == hash_invitation_token(first)
    assert first not in digest


def test_owner_invitation_is_rejected():
    with pytest.raises(ValueError):
        validate_invitation_role("owner")
    assert validate_invitation_role("cashier") == "cashier"


def test_invitation_lifetime_bound():
    assert invitation_expires_at() > datetime.now(timezone.utc)
    with pytest.raises(ValueError):
        invitation_expires_at(1000)
