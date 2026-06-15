from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from email_order_reader.models import OrderRow


@dataclass(frozen=True)
class OrderCache:
    email: str = ""
    uidvalidity: str = ""
    last_uid: int = 0
    rows: list[OrderRow] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    scanned_messages: int = 0
    parsed_attachments: int = 0


def load_order_cache(path: Path) -> OrderCache:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return OrderCache()

    if not isinstance(raw, dict):
        return OrderCache()

    return OrderCache(
        email=str(raw.get("email") or "").strip(),
        uidvalidity=str(raw.get("uidvalidity") or ""),
        last_uid=_to_int(raw.get("last_uid")),
        rows=_load_rows(raw.get("rows")),
        warnings=[str(warning) for warning in raw.get("warnings") or []],
        scanned_messages=_to_int(raw.get("scanned_messages")),
        parsed_attachments=_to_int(raw.get("parsed_attachments")),
    )


def save_order_cache(cache: OrderCache, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "email": cache.email,
                "uidvalidity": cache.uidvalidity,
                "last_uid": cache.last_uid,
                "rows": [_dump_row(row) for row in cache.rows],
                "warnings": cache.warnings,
                "scanned_messages": cache.scanned_messages,
                "parsed_attachments": cache.parsed_attachments,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


def _load_rows(raw_rows: object) -> list[OrderRow]:
    if not isinstance(raw_rows, list):
        return []

    rows: list[OrderRow] = []
    for raw_row in raw_rows:
        if not isinstance(raw_row, dict):
            continue
        order_number = str(raw_row.get("order_number") or "").strip()
        deadline = str(raw_row.get("deadline") or "").strip()
        if not order_number or not deadline:
            continue
        rows.append(
            OrderRow(
                order_number=order_number,
                deadline=deadline,
                source_file=str(raw_row.get("source_file") or ""),
                message_subject=str(raw_row.get("message_subject") or ""),
            )
        )
    return rows


def _dump_row(row: OrderRow) -> dict[str, str]:
    return {
        "order_number": row.order_number,
        "deadline": row.deadline,
        "source_file": row.source_file,
        "message_subject": row.message_subject,
    }


def _to_int(value: object) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0
