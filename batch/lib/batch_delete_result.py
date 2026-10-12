"""批量删除结果。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class BatchDeleteResult:
    total: int = 0
    matched_count: int = 0
    deleted_count: int = 0
    skipped_count: int = 0
    failed_count: int = 0
    dry_run: bool = True
    items: list[dict[str, Any]] = field(default_factory=list)
    extra: dict[str, Any] = field(default_factory=dict)
