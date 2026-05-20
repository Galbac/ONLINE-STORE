from source.db.models.choises.enum import UserRole
from source.services.admin_auth import ADMIN_PERMISSIONS_BY_ROLE, STAFF_ROLES


ROLE_DESCRIPTIONS = {
    UserRole.ADMIN: "Полный доступ",
    UserRole.MANAGER: "Работа с заказами и управлением магазина",
    UserRole.CONTENT_MANAGER: "Управление каталогом и контентом",
    UserRole.PICKER: "Сборка заказов",
    UserRole.COURIER: "Доставка заказов",
}

STAFF_ROLE_ORDER = (
    UserRole.ADMIN,
    UserRole.MANAGER,
    UserRole.CONTENT_MANAGER,
    UserRole.PICKER,
    UserRole.COURIER,
)


class RoleRepository:
    async def get_admin_roles(self, *, session=None) -> list[dict]:
        return [
            {
                "code": role.value,
                "name": role.label(),
                "description": ROLE_DESCRIPTIONS[role],
            }
            for role in STAFF_ROLE_ORDER
            if role in STAFF_ROLES
        ]

    async def get_by_code(self, *, session=None, code: str) -> UserRole | None:
        try:
            return UserRole(code)
        except ValueError:
            return None


class UserRoleRepository:
    async def update_role(self, *, session, user, role: UserRole):
        user.role = role
        session.add(user)
        await session.flush()
        await session.refresh(user)
        return user


class PermissionRepository:
    async def get_by_role_codes(self, *, session=None, role_codes: list[str]) -> dict[str, list[str]]:
        return {
            role.value: ADMIN_PERMISSIONS_BY_ROLE.get(role, [])
            for role in STAFF_ROLE_ORDER
            if role.value in role_codes
        }
