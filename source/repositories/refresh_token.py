from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from source.db.models.refresh_token import RefreshToken


class RefreshTokenRepository:
    async def create(
        self,
        *,
        session: AsyncSession,
        user_id: int,
        token_hash: str,
        expires_at: datetime,
    ) -> RefreshToken:
        refresh_token = RefreshToken(
            user_id=user_id,
            token_hash=token_hash,
            expires_at=expires_at,
        )
        session.add(refresh_token)
        await session.flush()
        await session.refresh(refresh_token)
        return refresh_token

    async def get_by_hash(
        self,
        *,
        session: AsyncSession,
        token_hash: str,
    ) -> RefreshToken | None:
        result = await session.execute(select(RefreshToken).where(RefreshToken.token_hash == token_hash))
        return result.scalar_one_or_none()

    async def revoke(
        self,
        *,
        session: AsyncSession,
        refresh_token: RefreshToken,
        revoked_at: datetime,
    ) -> RefreshToken:
        refresh_token.revoked_at = revoked_at
        session.add(refresh_token)
        await session.flush()
        await session.refresh(refresh_token)
        return refresh_token
