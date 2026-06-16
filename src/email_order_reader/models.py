from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass(frozen=True)
class OrderRow:
    order_number: str
    deadline: str
    source_file: str = ""
    message_subject: str = ""
    message_date: datetime | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "order_number", str(self.order_number).strip())
        object.__setattr__(self, "deadline", str(self.deadline).strip())
        object.__setattr__(self, "source_file", str(self.source_file).strip())
        object.__setattr__(self, "message_subject", str(self.message_subject).strip())
        object.__setattr__(self, "message_date", _normalize_message_date(self.message_date))


@dataclass(frozen=True)
class ColumnAliases:
    order_number: tuple[str, ...]
    deadline: tuple[str, ...]

    @classmethod
    def default(cls) -> "ColumnAliases":
        return cls(
            order_number=(
                "订单号",
                "订单编号",
                "客户订单号",
                "Order No",
                "Order Number",
                "PO",
                "PO Number",
            ),
            deadline=(
                "交单日期",
                "截至时间",
                "截止时间",
                "交货日期",
                "Delivery Date",
                "Due Date",
            ),
        )


@dataclass(frozen=True)
class EmailAttachment:
    filename: str
    content: bytes
    message_subject: str = ""
    message_date: datetime | None = None
    message_uid: str = ""


@dataclass(frozen=True)
class AttachmentFetchResult:
    attachments: list[EmailAttachment] = field(default_factory=list)
    scanned_messages: int = 0
    parsed_message_uids: list[str] = field(default_factory=list)
    latest_uid: int = 0
    uidvalidity: str = ""


@dataclass(frozen=True)
class AttachmentParseResult:
    filename: str
    rows: list[OrderRow] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class ScanResult:
    rows: list[OrderRow] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    scanned_messages: int = 0
    parsed_attachments: int = 0
    scan_mode: str = "full"

    @property
    def row_count(self) -> int:
        return len(self.rows)

    @property
    def warning_count(self) -> int:
        return len(self.warnings)


@dataclass(frozen=True)
class ImapConfig:
    server: str
    email: str
    auth_code: str
    port: int = 993


def _normalize_message_date(value: object) -> datetime | None:
    if value is None or isinstance(value, datetime):
        return value

    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        try:
            return datetime.fromisoformat(text)
        except ValueError:
            return None

    return None
