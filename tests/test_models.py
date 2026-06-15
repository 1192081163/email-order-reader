from datetime import datetime, timezone

from email_order_reader.models import (
    AttachmentParseResult,
    ColumnAliases,
    EmailAttachment,
    ImapConfig,
    OrderRow,
    ScanResult,
)


def test_order_row_strips_whitespace():
    row = OrderRow(order_number="  PO-1001  ", deadline=" 2026-06-20 ")

    assert row.order_number == "PO-1001"
    assert row.deadline == "2026-06-20"


def test_default_aliases_include_chinese_and_english_names():
    aliases = ColumnAliases.default()

    assert "订单号" in aliases.order_number
    assert "Order Number" in aliases.order_number
    assert "交单日期" in aliases.deadline
    assert "Due Date" in aliases.deadline


def test_scan_result_counts_rows_and_warnings():
    result = ScanResult(
        rows=[OrderRow("A1", "2026-06-20")],
        warnings=["未识别列：orders.xlsx"],
        scanned_messages=3,
        parsed_attachments=1,
    )

    assert result.row_count == 1
    assert result.warning_count == 1


def test_email_attachment_keeps_source_metadata():
    message_time = datetime(2026, 6, 15, 8, 30, tzinfo=timezone.utc)
    attachment = EmailAttachment(
        filename="orders.xlsx",
        content=b"content",
        message_subject="供应商订单",
        message_date=message_time,
    )

    assert attachment.filename == "orders.xlsx"
    assert attachment.message_subject == "供应商订单"
    assert attachment.message_date == message_time


def test_imap_config_defaults_to_ssl_port():
    config = ImapConfig(server="imap.example.com", email="a@example.com", auth_code="secret")

    assert config.port == 993
