from datetime import UTC, datetime


class RefreshTokenService:
    async def revoke_all_user_tokens(
        self,
        *,
        session,
        refresh_token_repository,
        user_id: int,
    ) -> int:
        return await refresh_token_repository.revoke_all_by_user_id(
            session=session,
            user_id=user_id,
            revoked_at=datetime.now(UTC),
        )
