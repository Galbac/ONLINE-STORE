from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True, slots=True)
class Pagination:
    offset: Optional[int] = None
    limit: Optional[int] = None
