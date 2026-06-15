from __future__ import annotations

import re
from datetime import date, datetime
from io import BytesIO
from pathlib import Path
from typing import Iterable, Sequence

from openpyxl import load_workbook

from email_order_reader.models import AttachmentParseResult, ColumnAliases, OrderRow


HEADER_SCAN_LIMIT = 20


def parse_excel_attachment(
    filename: str,
    content: bytes,
    aliases: ColumnAliases | None = None,
    message_subject: str = "",
) -> AttachmentParseResult:
    aliases = aliases or ColumnAliases.default()

    try:
        rows = _read_rows(filename, content)
    except Exception as exc:
        return AttachmentParseResult(filename=filename, warnings=[f"{filename}：无法读取Excel附件：{exc}"])

    return _parse_rows(filename, rows, aliases, message_subject)


def _read_rows(filename: str, content: bytes) -> list[list[object]]:
    suffix = Path(filename).suffix.lower()
    if suffix in {".xlsx", ".xlsm"}:
        return _read_openpyxl_rows(content)
    return []


def _read_openpyxl_rows(content: bytes) -> list[list[object]]:
    workbook = load_workbook(BytesIO(content), read_only=True, data_only=True)
    rows: list[list[object]] = []
    try:
        for sheet in workbook.worksheets:
            for row in sheet.iter_rows(values_only=True):
                rows.append(list(row))
    finally:
        workbook.close()
    return rows


def _parse_rows(
    filename: str,
    rows: Sequence[Sequence[object]],
    aliases: ColumnAliases,
    message_subject: str,
) -> AttachmentParseResult:
    header_match = _find_header(rows, aliases)
    if header_match is None:
        return AttachmentParseResult(filename=filename, warnings=[f"{filename}：未识别订单号列或截至时间列"])

    header_index, order_col, deadline_col = header_match
    parsed_rows: list[OrderRow] = []

    for row in rows[header_index + 1 :]:
        order_number = _cell_to_text(_get_cell(row, order_col))
        deadline = _normalize_deadline(_get_cell(row, deadline_col))
        if not order_number or not deadline:
            continue

        parsed_rows.append(
            OrderRow(
                order_number=order_number,
                deadline=deadline,
                source_file=filename,
                message_subject=message_subject,
            )
        )

    return AttachmentParseResult(filename=filename, rows=parsed_rows)


def _find_header(
    rows: Sequence[Sequence[object]],
    aliases: ColumnAliases,
) -> tuple[int, int, int] | None:
    order_aliases = {_normalize_header(value) for value in aliases.order_number}
    deadline_aliases = {_normalize_header(value) for value in aliases.deadline}

    for index, row in enumerate(rows[:HEADER_SCAN_LIMIT]):
        normalized = [_normalize_header(_cell_to_text(cell)) for cell in row]
        order_col = _find_first_index(normalized, order_aliases)
        deadline_col = _find_first_index(normalized, deadline_aliases)
        if order_col is not None and deadline_col is not None:
            return index, order_col, deadline_col

    return None


def _find_first_index(values: Iterable[str], targets: set[str]) -> int | None:
    for index, value in enumerate(values):
        if value in targets:
            return index
    return None


def _normalize_header(value: object) -> str:
    text = _cell_to_text(value).lower()
    return re.sub(r"[\s_\-:/：（）()]+", "", text)


def _get_cell(row: Sequence[object], index: int) -> object:
    if index >= len(row):
        return None
    return row[index]


def _cell_to_text(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value).strip()


def _normalize_deadline(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()

    text = _cell_to_text(value)
    if not text:
        return ""

    patterns = (
        r"^(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})$",
        r"^(\d{4})年(\d{1,2})月(\d{1,2})日$",
    )
    for pattern in patterns:
        match = re.match(pattern, text)
        if match:
            year, month, day = (int(part) for part in match.groups())
            return date(year, month, day).isoformat()

    return text
