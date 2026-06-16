from datetime import datetime, timedelta, timezone
from email.message import EmailMessage

from email_order_reader.email_client import (
    ImapEmailClient,
    extract_excel_attachments,
    imap_since_date,
    is_excel_filename,
    parse_message_date,
)
from email_order_reader.models import ImapConfig


def test_imap_since_date_uses_cutoff_calendar_date():
    now = datetime(2026, 6, 15, 10, 30, tzinfo=timezone.utc)

    assert imap_since_date(now - timedelta(hours=24)) == "14-Jun-2026"


def test_is_excel_filename_accepts_supported_formats():
    assert is_excel_filename("orders.xlsx")
    assert is_excel_filename("orders.xlsm")
    assert is_excel_filename("orders.xls")
    assert not is_excel_filename("orders.csv")


def test_extract_excel_attachments_decodes_filename_and_payload():
    message = EmailMessage()
    message["Subject"] = "供应商订单"
    message["Date"] = "Mon, 15 Jun 2026 10:00:00 +0000"
    message.set_content("see attachment")
    message.add_attachment(
        b"excel-bytes",
        maintype="application",
        subtype="vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        filename="orders.xlsx",
    )
    message.add_attachment(
        b"text-bytes",
        maintype="text",
        subtype="plain",
        filename="notes.txt",
    )

    attachments = extract_excel_attachments(message)

    assert len(attachments) == 1
    assert attachments[0].filename == "orders.xlsx"
    assert attachments[0].content == b"excel-bytes"
    assert attachments[0].message_subject == "供应商订单"
    assert attachments[0].message_date == datetime(2026, 6, 15, 10, 0, tzinfo=timezone.utc)


def test_parse_message_date_returns_none_for_missing_date():
    message = EmailMessage()

    assert parse_message_date(message) is None


def test_imap_client_fetches_all_inbox_messages_without_date_filter(monkeypatch):
    message = EmailMessage()
    message["Subject"] = "旧订单"
    message["Date"] = "Mon, 15 Jun 2020 10:00:00 +0000"
    message.set_content("see attachment")
    message.add_attachment(
        b"excel-bytes",
        maintype="application",
        subtype="vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        filename="old-orders.xlsx",
    )
    mailbox = FakeMailbox(message.as_bytes())

    monkeypatch.setattr(
        "email_order_reader.email_client.imaplib.IMAP4_SSL",
        lambda server, port, timeout: mailbox,
    )

    client = ImapEmailClient(ImapConfig(server="imap.example.com", email="buyer@example.com", auth_code="secret"))
    attachments, scanned_messages = client.fetch_excel_attachments()

    assert mailbox.search_calls == [(None, "ALL")]
    assert scanned_messages == 1
    assert [attachment.filename for attachment in attachments] == ["old-orders.xlsx"]


def test_imap_client_ignores_logout_eof_after_fetching_messages(monkeypatch):
    message = EmailMessage()
    message["Subject"] = "旧订单"
    message["Date"] = "Mon, 15 Jun 2020 10:00:00 +0000"
    message.set_content("see attachment")
    message.add_attachment(
        b"excel-bytes",
        maintype="application",
        subtype="vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        filename="old-orders.xlsx",
    )
    mailbox = FakeLogoutEofMailbox(message.as_bytes())

    monkeypatch.setattr(
        "email_order_reader.email_client.imaplib.IMAP4_SSL",
        lambda server, port, timeout: mailbox,
    )

    client = ImapEmailClient(ImapConfig(server="imap.example.com", email="buyer@example.com", auth_code="secret"))
    attachments, scanned_messages = client.fetch_excel_attachments()

    assert scanned_messages == 1
    assert [attachment.filename for attachment in attachments] == ["old-orders.xlsx"]
    assert mailbox.logout_called


def test_imap_client_fetches_incremental_messages_by_uid(monkeypatch):
    message = EmailMessage()
    message["Subject"] = "新订单"
    message["Date"] = "Mon, 15 Jun 2026 10:00:00 +0000"
    message.set_content("see attachment")
    message.add_attachment(
        b"excel-bytes",
        maintype="application",
        subtype="vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        filename="new-orders.xlsx",
    )
    mailbox = FakeUidMailbox(message.as_bytes())

    monkeypatch.setattr(
        "email_order_reader.email_client.imaplib.IMAP4_SSL",
        lambda server, port, timeout: mailbox,
    )

    client = ImapEmailClient(ImapConfig(server="imap.example.com", email="buyer@example.com", auth_code="secret"))
    result = client.fetch_excel_attachment_batch(since_uid=41)

    assert mailbox.uid_calls[0] == ("SEARCH", None, "UID", "42:*")
    assert mailbox.uid_calls[1] == ("FETCH", b"42", "(RFC822)")
    assert result.scanned_messages == 1
    assert result.latest_uid == 42
    assert result.uidvalidity == "uid-validity-1"
    assert result.parsed_message_uids == ["42"]
    assert [(attachment.filename, attachment.message_uid) for attachment in result.attachments] == [
        ("new-orders.xlsx", "42")
    ]


def test_imap_client_ignores_logout_eof_after_incremental_fetch(monkeypatch):
    message = EmailMessage()
    message["Subject"] = "新订单"
    message["Date"] = "Mon, 15 Jun 2026 10:00:00 +0000"
    message.set_content("see attachment")
    message.add_attachment(
        b"excel-bytes",
        maintype="application",
        subtype="vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        filename="new-orders.xlsx",
    )
    mailbox = FakeLogoutEofUidMailbox(message.as_bytes())

    monkeypatch.setattr(
        "email_order_reader.email_client.imaplib.IMAP4_SSL",
        lambda server, port, timeout: mailbox,
    )

    client = ImapEmailClient(ImapConfig(server="imap.example.com", email="buyer@example.com", auth_code="secret"))
    result = client.fetch_excel_attachment_batch(since_uid=41)

    assert result.scanned_messages == 1
    assert [(attachment.filename, attachment.message_uid) for attachment in result.attachments] == [
        ("new-orders.xlsx", "42")
    ]
    assert mailbox.logout_called


class FakeMailbox:
    def __init__(self, raw_message: bytes):
        self.raw_message = raw_message
        self.search_calls = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def logout(self):
        self.logout_called = True
        return "OK", [b"LOGOUT"]

    def login(self, email, auth_code):
        self.email = email
        self.auth_code = auth_code

    def select(self, mailbox):
        self.selected_mailbox = mailbox

    def search(self, *criteria):
        self.search_calls.append(criteria)
        return "OK", [b"1"]

    def fetch(self, message_id, query):
        return "OK", [(b"RFC822", self.raw_message)]


class FakeLogoutEofMailbox(FakeMailbox):
    def __init__(self, raw_message: bytes):
        super().__init__(raw_message)
        self.logout_called = False

    def __exit__(self, exc_type, exc, traceback):
        self.logout()

    def logout(self):
        from imaplib import IMAP4

        self.logout_called = True
        raise IMAP4.abort("command: LOGOUT => socket error: EOF")


class FakeUidMailbox:
    def __init__(self, raw_message: bytes):
        self.raw_message = raw_message
        self.uid_calls = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def logout(self):
        self.logout_called = True
        return "OK", [b"LOGOUT"]

    def login(self, email, auth_code):
        self.email = email
        self.auth_code = auth_code

    def select(self, mailbox):
        self.selected_mailbox = mailbox
        return "OK", [b"1"]

    def response(self, code):
        if code == "UIDVALIDITY":
            return "OK", [b"uid-validity-1"]
        return "OK", []

    def uid(self, *args):
        self.uid_calls.append(args)
        if args[0] == "SEARCH":
            return "OK", [b"42"]
        if args[0] == "FETCH":
            return "OK", [(b"42 (RFC822 {1}", self.raw_message)]
        return "NO", []


class FakeLogoutEofUidMailbox(FakeUidMailbox):
    def __init__(self, raw_message: bytes):
        super().__init__(raw_message)
        self.logout_called = False

    def __exit__(self, exc_type, exc, traceback):
        self.logout()

    def logout(self):
        from imaplib import IMAP4

        self.logout_called = True
        raise IMAP4.abort("command: LOGOUT => socket error: EOF")
