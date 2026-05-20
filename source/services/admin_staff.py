from datetime import datetime

from source.config.settings import settings
from source.db.models.choises.enum import UserRole
from source.errors.auth import (
    AdminAuthAccessDeniedError,
    AdminStaffInvalidRoleError,
    AdminStaffNotFoundError,
    EmptyAdminStaffUpdateError,
    InactiveUserError,
    LastActiveAdminDeactivationError,
    UserEmailAlreadyExistsError,
    UserPhoneAlreadyExistsError,
)
from source.schemas.pydantic.admin_staff import (
    AdminStaffCreateRequest,
    AdminStaffDetailResponse,
    AdminStaffListItemResponse,
    AdminStaffListQueryParams,
    AdminStaffListResponse,
    AdminStaffUpdateRequest,
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

    def _check_create_permission(self, *, user, permission_service) -> None:
        if not user.is_active or user.is_deleted or user.is_blocked:
            raise InactiveUserError
        if user.role not in STAFF_ROLES:
            raise AdminAuthAccessDeniedError
        if "admin:staff:create" not in permission_service.get_user_permissions(role=user.role):
            raise AdminAuthAccessDeniedError

    def _check_update_permission(self, *, user, permission_service) -> None:
        if not user.is_active or user.is_deleted or user.is_blocked:
            raise InactiveUserError
        if user.role not in STAFF_ROLES:
            raise AdminAuthAccessDeniedError
        if "admin:staff:update" not in permission_service.get_user_permissions(role=user.role):
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

    async def get_staff_detail(
        self,
        *,
        session,
        redis_service: RedisService,
        user,
        staff_id: int,
        permission_service,
        user_repository,
        admin_staff_cache_service,
    ) -> AdminStaffDetailResponse:
        self._check_read_permission(user=user, permission_service=permission_service)

        cached_staff = await admin_staff_cache_service.get_detail(
            redis_service=redis_service,
            staff_id=staff_id,
        )
        if cached_staff is not None:
            return cached_staff

        staff = await user_repository.get_by_id(session=session, user_id=staff_id)
        if staff is None or staff.role not in STAFF_ROLES:
            raise AdminStaffNotFoundError

        response = self._build_staff_detail_response(
            user=staff,
            permissions=permission_service.get_user_permissions(role=staff.role),
        )
        await admin_staff_cache_service.set_detail(
            redis_service=redis_service,
            staff_id=staff.id,
            response=response,
            ttl_seconds=settings.admin_staff.list_cache_ttl_seconds,
        )
        return response

    async def create_staff(
        self,
        *,
        session,
        redis_service: RedisService,
        user,
        data: AdminStaffCreateRequest,
        commiter,
        permission_service,
        user_repository,
        password_service,
        admin_audit_log_repository,
        admin_staff_cache_service,
    ) -> AdminStaffDetailResponse:
        self._check_create_permission(user=user, permission_service=permission_service)

        if data.role not in STAFF_ROLES:
            raise AdminStaffInvalidRoleError
        if not permission_service.validate_role_assignable(actor_role=user.role, target_role=data.role):
            raise AdminStaffInvalidRoleError

        existing_user = await user_repository.get_by_phone(session=session, phone=data.phone)
        if existing_user is not None:
            raise UserPhoneAlreadyExistsError
        if data.email is not None:
            existing_user = await user_repository.get_by_email(session=session, email=data.email)
            if existing_user is not None:
                raise UserEmailAlreadyExistsError

        created_user = await user_repository.create(
            session=session,
            name=data.name,
            email=data.email,
            phone=data.phone,
            password_hash=password_service.hash_password(data.password),
            role=data.role,
            is_active=data.is_active,
            is_blocked=False,
        )
        await admin_audit_log_repository.create(
            session=session,
            user_id=user.id,
            login=getattr(user, "email", None) or getattr(user, "phone", None) or str(user.id),
            event="admin_staff_create",
            status="success",
            details={
                "target_user_id": created_user.id,
                "role": created_user.role.value,
            },
        )
        await commiter.commit()

        await admin_staff_cache_service.invalidate_all(redis_service=redis_service)
        await redis_service.delete_by_pattern("admin:roles:*")

        return AdminStaffDetailResponse(
            id=created_user.id,
            name=created_user.name,
            email=created_user.email,
            phone=created_user.phone,
            role=created_user.role,
            permissions=permission_service.get_user_permissions(role=created_user.role),
            is_active=created_user.is_active,
            is_blocked=created_user.is_blocked,
            last_login_at=getattr(created_user, "last_login_at", None),
            created_at=created_user.created_date,
            updated_at=getattr(created_user, "updated_date", None),
        )

    async def update_staff(
        self,
        *,
        session,
        redis_service: RedisService,
        user,
        staff_id: int,
        data: AdminStaffUpdateRequest,
        commiter,
        permission_service,
        user_repository,
        audit_log_service,
        admin_audit_log_repository,
        admin_staff_cache_service,
        admin_auth_cache_service,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> AdminStaffDetailResponse:
        self._check_update_permission(user=user, permission_service=permission_service)

        update_fields = data.model_dump(exclude_unset=True)
        if not update_fields:
            raise EmptyAdminStaffUpdateError

        staff = await user_repository.get_by_id(session=session, user_id=staff_id)
        if staff is None or staff.role not in STAFF_ROLES:
            raise AdminStaffNotFoundError

        if "phone" in update_fields and update_fields["phone"] != staff.phone:
            existing_user = await user_repository.get_by_phone(session=session, phone=update_fields["phone"])
            if existing_user is not None and existing_user.id != staff.id:
                raise UserPhoneAlreadyExistsError
        if "email" in update_fields and update_fields["email"] != staff.email:
            email = update_fields["email"]
            if email is not None:
                existing_user = await user_repository.get_by_email(session=session, email=email)
                if existing_user is not None and existing_user.id != staff.id:
                    raise UserEmailAlreadyExistsError

        if (
            staff.id == user.id
            and staff.role == UserRole.ADMIN
            and staff.is_active
            and update_fields.get("is_active") is False
        ):
            active_admins = await user_repository.count_active_admins(session=session)
            if active_admins <= 1:
                raise LastActiveAdminDeactivationError

        before = {
            field: getattr(staff, field)
            for field in update_fields
        }
        for field, value in update_fields.items():
            setattr(staff, field, value)
        staff.updated_date = datetime.now(settings.tz)
        updated_staff = await user_repository.update(session=session, user=staff)

        changes = {
            field: {
                "old": str(before[field]) if before[field] is not None else None,
                "new": str(getattr(updated_staff, field)) if getattr(updated_staff, field) is not None else None,
            }
            for field in update_fields
            if before[field] != getattr(updated_staff, field)
        }
        await audit_log_service.log_action(
            session=session,
            audit_log_repository=admin_audit_log_repository,
            user_id=user.id,
            login=getattr(user, "email", None) or getattr(user, "phone", None) or str(user.id),
            event="admin_staff_update",
            status="success",
            ip_address=ip_address,
            user_agent=user_agent,
            details={
                "target_user_id": updated_staff.id,
                "changes": changes,
            },
        )
        await commiter.commit()

        await admin_staff_cache_service.invalidate_all(redis_service=redis_service)
        await admin_auth_cache_service.invalidate_me(redis_service=redis_service, user_id=updated_staff.id)

        return self._build_staff_detail_response(
            user=updated_staff,
            permissions=permission_service.get_user_permissions(role=updated_staff.role),
        )

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

    def _build_staff_detail_response(self, *, user, permissions: list[str]) -> AdminStaffDetailResponse:
        return AdminStaffDetailResponse(
            id=user.id,
            name=user.name,
            email=user.email,
            phone=user.phone,
            role=user.role,
            permissions=permissions,
            is_active=user.is_active,
            is_blocked=user.is_blocked,
            last_login_at=getattr(user, "last_login_at", None),
            created_at=user.created_date,
            updated_at=getattr(user, "updated_date", None),
        )
