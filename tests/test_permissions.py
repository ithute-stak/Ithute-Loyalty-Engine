from loyalty_api.permissions import Permission, has_permission


def test_cashier_cannot_manage_users():
    assert not has_permission({"cashier"}, Permission.USERS_MANAGE)
    assert has_permission({"cashier"}, Permission.POINTS_REDEEM)


def test_unknown_role_denied():
    assert not has_permission({"not-a-role"}, Permission.COMPANY_READ)


def test_auditor_cannot_issue_points():
    assert not has_permission({"auditor"}, Permission.POINTS_ISSUE)


def test_owner_has_admin_permissions():
    assert has_permission({"owner"}, Permission.USERS_MANAGE)
