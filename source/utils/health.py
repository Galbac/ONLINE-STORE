from sqlalchemy import text


class DatabaseHealthChecker:
    async def check(self, *, session) -> None:
        await session.execute(text("SELECT 1"))
