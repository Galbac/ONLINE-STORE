from source.config.settings import settings
from source.errors.auth import AdminAuthAccessDeniedError, InactiveUserError
from source.schemas.pydantic.admin_staff import (
    AdminStaffListItemResponse,
    AdminStaffListQueryParams,
    AdminStaffListResponse,
)
from source.services.admin_auth import STAFF_ROLES
from source.services.redis import RedisService
from source.utils.query_hash import build_query_hash
from source.utils.search import normalize_search_query


class AdminStaffService:
    def _check_read_permission(self, *, user, permission_service) -> None:
        if not user.is_active or user.is_deleted or user.is_blocked:
            raise InactiveUserError
        if user.role not in STAFF_ROLES:
            raise AdminAuthAccessDeniedError
        if "admin:staff:read" not in permission_service.get_user_permissions(role=user.role):
            raise AdminAuthAccessDeniedError

    async def get_staff_list(
        self,
        *,
        session,
        redis_service: RedisService,
        user,
        query: AdminStaffListQueryParams,
        permission_service,
        user_repository,
        admin_staff_cache_service,
    ) -> AdminStaffListResponse:
        self._check_read_permission(user=user, permission_service=permission_service)

        normalized_query = query.model_copy(
            update={"q": normalize_search_query(query.q) if query.q is not None else None},
        )
        query_hash = build_query_hash(normalized_query.model_dump())
        cached_staff = await admin_staff_cache_service.get_list(
            redis_service=redis_service,
            query_hash=query_hash,
        )
        if cached_staff is not None:
            return cached_staff

        staff = await user_repository.admin_get_staff_list(session=session, query=normalized_query)
        total = await user_repository.admin_count_staff(session=session, query=normalized_query)
        response = AdminStaffListResponse.build(
            items=[self._build_staff_response(user=staff_user) for staff_user in staff],
            total=total,
            page=normalized_query.page,
            limit=normalized_query.limit,
        )
        await admin_staff_cache_service.set_list(
            redis_service=redis_service,
            query_hash=query_hash,
            response=response,
            ttl_seconds=settings.admin_staff.list_cache_ttl_seconds,
        )
        return response

    def _build_staff_response(self, *, user) -> AdminStaffListItemResponse:
        return AdminStaffListItemResponse(
            id=user.id,
            name=user.name,
            email=user.email,
            phone=user.phone,
            role=user.role,
            is_active=user.is_active,
            is_blocked=user.is_blocked,
            created_at=user.created_date,
        )
