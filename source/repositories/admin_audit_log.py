from sqlalchemy.ext.asyncio import AsyncSession

from source.db.models.admin_audit_log import AdminAuditLog


class AdminAuditLogRepository:
    async def create(self, *, session: AsyncSession, **data) -> AdminAuditLog:
        log = AdminAuditLog(**data)
        session.add(log)
        await session.flush()
        await session.refresh(log)
        return log
