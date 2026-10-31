"""Pure permission policy; does not authenticate users.

Roles are company-specific and must be assigned by verified platform/company
administrators. API keys alone must NOT imply owner or administrator permissions.
"""
from enum import StrEnum


class Permission(StrEnum):
    COMPANY_READ = "company:read"
    COMPANY_MANAGE = "company:manage"
    USERS_MANAGE = "users:manage"
    BRANCH_READ = "branch:read"
    BRANCH_MANAGE = "branch:manage"
    PROGRAMME_READ = "programme:read"
    PROGRAMME_MANAGE = "programme:manage"
    POINTS_READ = "points:read"
    POINTS_ISSUE = "points:issue"
    POINTS_REDEEM = "points:redeem"


ROLE_PERMISSIONS: dict[str, frozenset[Permission]] = {
    "owner": frozenset(Permission),
    "administrator": frozenset({
        Permission.COMPANY_READ, Permission.USERS_MANAGE, Permission.BRANCH_READ,
        Permission.BRANCH_MANAGE, Permission.PROGRAMME_READ, Permission.PROGRAMME_MANAGE,
        Permission.POINTS_READ,
    }),
    "branch_manager": frozenset({
        Permission.BRANCH_READ, Permission.PROGRAMME_READ, Permission.POINTS_READ,
        Permission.POINTS_ISSUE, Permission.POINTS_REDEEM,
    }),
    "cashier": frozenset({
        Permission.BRANCH_READ, Permission.POINTS_ISSUE, Permission.POINTS_REDEEM,
    }),
    "auditor": frozenset({
        Permission.COMPANY_READ, Permission.BRANCH_READ, Permission.PROGRAMME_READ,
        Permission.POINTS_READ,
    }),
}


def has_permission(role_codes: set[str], permission: Permission) -> bool:
    return any(permission in ROLE_PERMISSIONS.get(role, frozenset()) for role in role_codes)
