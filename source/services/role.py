from source.config.settings import settings
from source.errors.auth import AdminAuthAccessDeniedError, InactiveUserError
from source.schemas.pydantic.admin_role import AdminRoleListResponse, AdminRoleResponse
from source.services.admin_auth import STAFF_ROLES
from source.services.redis import RedisService


class RoleService:
    cache_key = "admin:roles:list"

    def _check_read_permission(self, *, user, permission_service) -> None:
        if not user.is_active or user.is_deleted or user.is_blocked:
            raise InactiveUserError
        if user.role not in STAFF_ROLES:
            raise AdminAuthAccessDeniedError
        permissions = permission_service.get_user_permissions(role=user.role)
        if "admin:roles:read" not in permissions and "admin:staff:read" not in permissions:
            raise AdminAuthAccessDeniedError

    async def get_admin_roles(
        self,
        *,
        session,
        redis_service: RedisService,
        user,
        permission_service,
        role_repository,
        permission_repository,
    ) -> AdminRoleListResponse:
        self._check_read_permission(user=user, permission_service=permission_service)

        cached_roles = await redis_service.get(self.cache_key)
        if cached_roles is not None:
            if isinstance(cached_roles, bytes):
                cached_roles = cached_roles.decode("utf-8")
            return AdminRoleListResponse.model_validate_json(cached_roles)

        staff_role_codes = {role.value for role in STAFF_ROLES}
        roles = [
            role
            for role in await role_repository.get_admin_roles(session=session)
            if role["code"] in staff_role_codes
        ]
        permissions_by_role = await permission_repository.get_by_role_codes(
            session=session,
            role_codes=[role["code"] for role in roles],
        )
        response = AdminRoleListResponse(
            items=[
                AdminRoleResponse(
                    code=role["code"],
                    name=role["name"],
                    description=role["description"],
                    permissions=permissions_by_role.get(role["code"], []),
                )
                for role in roles
            ],
        )
        await redis_service.set(
            self.cache_key,
            response.model_dump_json(),
            ttl_seconds=settings.admin_staff.roles_cache_ttl_seconds,
        )
        return response
