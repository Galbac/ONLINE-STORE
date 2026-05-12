from typing import Protocol


class Commiter(Protocol):
    async def commit(self) -> None:
        raise NotImplementedError

    async def begin(self) -> None:
        raise NotImplementedError

    async def rollback(self) -> None:
        raise NotImplementedError

    async def flush(self) -> None:
        raise NotImplementedError
