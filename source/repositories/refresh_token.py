from datetime import datetime

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
