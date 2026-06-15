from datetime import date
from io import BytesIO

from openpyxl import Workbook

from email_order_reader.models import ColumnAliases, EmailAttachment
from email_order_reader.order_cache import OrderCache, load_order_cache, save_order_cache
from email_order_reader.scan_service import OrderScanService


class FakeClient:
    def __init__(self, attachments, scanned_messages):
        self.attachments = attachments
        self.scanned_messages = scanned_messages
        self.hours = None

    def fetch_excel_attachments(self, hours=None):
        self.hours = hours
        return self.attachments, self.scanned_messages

    def fetch_recent_excel_attachments(self, hours=24):
        self.hours = hours
        return self.attachments, self.scanned_messages


class FakeBatchClient:
    def __init__(self, batch):
        self.batch = batch
        self.batch_calls = []

    def fetch_excel_attachments(self, hours=None):
        raise AssertionError("incremental scans should use batch fetching")

    def fetch_recent_excel_attachments(self, hours=24):
        raise AssertionError("incremental scans should use batch fetching")

    def fetch_excel_attachment_batch(self, hours=None, since_uid=None):
        self.batch_calls.append((hours, since_uid))
        return self.batch


def make_attachment(filename="orders.xlsx"):
    workbook = Workbook()
    sheet = workbook.active
    sheet.append(["订单号", "交单日期"])
    sheet.append(["PO-6006", date(2026, 10, 1)])
    stream = BytesIO()
    workbook.save(stream)
    return EmailAttachment(
        filename=filename,
        content=stream.getvalue(),
        message_subject="供应商订单",
    )


def test_scan_service_reads_all_orders_by_default():
    client = FakeClient([make_attachment()], scanned_messages=2)
    service = OrderScanService(client=client, aliases=ColumnAliases.default())

    result = service.scan_orders()

    assert client.hours is None
    assert result.scanned_messages == 2
    assert result.parsed_attachments == 1
    assert [(row.order_number, row.deadline) for row in result.rows] == [("PO-6006", "2026-10-01")]
    assert result.warnings == []


def test_scan_service_keeps_attachment_warnings():
    client = FakeClient([EmailAttachment(filename="bad.xlsx", content=b"bad")], scanned_messages=1)
    service = OrderScanService(client=client, aliases=ColumnAliases.default())

    result = service.scan_recent_orders(hours=24)

    assert result.rows == []
    assert result.parsed_attachments == 1
    assert result.warnings
    assert result.warnings[0].startswith("bad.xlsx：无法读取Excel附件")


def test_full_scan_writes_order_cache(tmp_path):
    from email_order_reader.models import AttachmentFetchResult

    cache_path = tmp_path / "order_cache.json"
    client = FakeBatchClient(
        AttachmentFetchResult(
            attachments=[make_attachment()],
            scanned_messages=4,
            parsed_message_uids=["8"],
            latest_uid=8,
            uidvalidity="uid-validity-1",
        )
    )
    service = OrderScanService(
        client=client,
        aliases=ColumnAliases.default(),
        cache_path=cache_path,
        account_email="buyer@example.com",
    )

    result = service.scan_orders(full_scan=True)

    cache = load_order_cache(cache_path)
    assert client.batch_calls == [(None, None)]
    assert result.scanned_messages == 4
    assert cache.email == "buyer@example.com"
    assert cache.last_uid == 8
    assert cache.uidvalidity == "uid-validity-1"
    assert [(row.order_number, row.deadline) for row in cache.rows] == [("PO-6006", "2026-10-01")]


def test_incremental_scan_reuses_cached_orders_and_fetches_only_new_uids(tmp_path):
    from email_order_reader.models import AttachmentFetchResult, OrderRow

    cache_path = tmp_path / "order_cache.json"
    save_order_cache(
        OrderCache(
            email="buyer@example.com",
            uidvalidity="uid-validity-1",
            last_uid=10,
            rows=[OrderRow(order_number="PO-OLD", deadline="2026-06-20")],
            scanned_messages=10,
            parsed_attachments=3,
        ),
        cache_path,
    )
    client = FakeBatchClient(
        AttachmentFetchResult(
            attachments=[make_attachment()],
            scanned_messages=1,
            parsed_message_uids=["11"],
            latest_uid=11,
            uidvalidity="uid-validity-1",
        )
    )
    service = OrderScanService(
        client=client,
        aliases=ColumnAliases.default(),
        cache_path=cache_path,
        account_email="buyer@example.com",
    )

    result = service.scan_orders(full_scan=False)

    assert client.batch_calls == [(None, 10)]
    assert result.scanned_messages == 11
    assert result.parsed_attachments == 4
    assert [(row.order_number, row.deadline) for row in result.rows] == [
        ("PO-OLD", "2026-06-20"),
        ("PO-6006", "2026-10-01"),
    ]
    assert load_order_cache(cache_path).last_uid == 11


def test_incremental_scan_falls_back_to_full_scan_for_different_cached_email(tmp_path):
    from email_order_reader.models import AttachmentFetchResult

    cache_path = tmp_path / "order_cache.json"
    save_order_cache(OrderCache(email="old@example.com", last_uid=10), cache_path)
    client = FakeBatchClient(
        AttachmentFetchResult(
            attachments=[make_attachment()],
            scanned_messages=2,
            parsed_message_uids=["12"],
            latest_uid=12,
            uidvalidity="uid-validity-1",
        )
    )
    service = OrderScanService(
        client=client,
        aliases=ColumnAliases.default(),
        cache_path=cache_path,
        account_email="buyer@example.com",
    )

    service.scan_orders(full_scan=False)

    assert client.batch_calls == [(None, None)]
