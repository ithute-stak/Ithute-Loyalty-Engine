import uuid

from loyalty_api.access import RoleGrant, authorized_grants, parse_bearer
from loyalty_api.permissions import Permission
from fastapi import HTTPException
import pytest


def test_branch_scope_cannot_escalate_to_company_level():
    branch_id = uuid.uuid4()
    grants = [RoleGrant("branch_manager", branch_id)]
    assert authorized_grants(grants, Permission.BRANCH_READ, branch_id)
    assert not authorized_grants(grants, Permission.BRANCH_READ, uuid.uuid4())
    assert not authorized_grants(grants, Permission.BRANCH_READ)


def test_global_owner_can_access_any_branch():
    grants = [RoleGrant("owner", None)]
    assert authorized_grants(grants, Permission.USERS_MANAGE)
    assert authorized_grants(grants, Permission.BRANCH_READ, uuid.uuid4())


def test_cashier_cannot_list_users():
    assert not authorized_grants([RoleGrant("cashier", None)], Permission.USERS_MANAGE)


def test_bearer_validation():
    assert parse_bearer("Bearer abc") == "abc"
    for value in (None, "Basic abc", "Bearer ", "Bearer  abc"):
        with pytest.raises(HTTPException):
            parse_bearer(value)
