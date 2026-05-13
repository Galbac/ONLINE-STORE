from hashlib import sha256
import json
from typing import Any


def build_query_hash(params: dict[str, Any]) -> str:
    normalized_params = {
        key: value.isoformat() if hasattr(value, "isoformat") else value
        for key, value in sorted(params.items())
        if value is not None
    }
    payload = json.dumps(normalized_params, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return sha256(payload.encode("utf-8")).hexdigest()
