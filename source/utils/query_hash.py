from hashlib import sha256
import json
from decimal import Decimal
from typing import Any


def _normalize_query_value(value: Any) -> Any:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, dict):
        return {
            key: _normalize_query_value(item)
            for key, item in sorted(value.items())
            if item is not None
        }
    if isinstance(value, list | tuple):
        return [_normalize_query_value(item) for item in value]
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return value


def build_query_hash(params: dict[str, Any]) -> str:
    normalized_params = {
        key: _normalize_query_value(value)
        for key, value in sorted(params.items())
        if value is not None
    }
    payload = json.dumps(normalized_params, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return sha256(payload.encode("utf-8")).hexdigest()
