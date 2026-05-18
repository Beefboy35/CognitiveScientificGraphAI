from __future__ import annotations

from dataclasses import asdict
from typing import Any


def dump(obj: Any) -> Any:
    if hasattr(obj, '__dataclass_fields__'):
        return asdict(obj)
    if isinstance(obj, list):
        return [dump(item) for item in obj]
    if isinstance(obj, dict):
        return {key: dump(value) for key, value in obj.items()}
    return obj
