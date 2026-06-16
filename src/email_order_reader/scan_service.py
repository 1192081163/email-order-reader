from __future__ import annotations

from pathlib import Path
from typing import Protocol

from email_order_reader.excel_parser import parse_excel_attachment
from email_order_reader.models import AttachmentFetchResult, ColumnAliases, EmailAttachment, OrderRow, ScanResult
from email_order_reader.order_cache import OrderCache, load_order_cache, save_order_cache


class RecentAttachmentClient(Protocol):
    def fetch_excel_attachments(self, hours: int | None = None) -> tuple[list[EmailAttachment], int]:
        pass

    def fetch_recent_excel_attachments(self, hours: int = 24) -> tuple[list[EmailAttachment], int]:
        pass

    def fetch_excel_attachment_batch(
        self,
        hours: int | None = None,
        since_uid: int | None = None,
    ) -> AttachmentFetchResult:
        pass


class OrderScanService:
    def __init__(
        self,
        client: RecentAttachmentClient,
        aliases: ColumnAliases | None = None,
        cache_path: Path | None = None,
        account_email: str = "",
    ) -> None:
        self.client = client
        self.aliases = aliases or ColumnAliases.default()
        self.cache_path = cache_path
        self.account_email = account_email.strip()

    def scan_orders(self, hours: int | None = None, full_scan: bool = True) -> ScanResult:
        if self.cache_path is not None and hours is None:
            if full_scan:
                return self._scan_full_with_cache()
            return self._scan_incremental_with_cache()

        attachments, scanned_messages = self.client.fetch_excel_attachments(hours=hours)
        return self._parse_attachments(attachments, scanned_messages, scan_mode="full")

    def _scan_full_with_cache(self) -> ScanResult:
        batch = self.client.fetch_excel_attachment_batch()
        result = self._parse_attachments(batch.attachments, batch.scanned_messages, scan_mode="full")
        self._save_cache(batch, result)
        return result

    def _scan_incremental_with_cache(self) -> ScanResult:
        cache = load_order_cache(self.cache_path)
        if not self._cache_matches_account(cache) or cache.last_uid <= 0 or _has_legacy_rows_without_message_dates(cache.rows):
            return self._scan_full_with_cache()

        batch = self.client.fetch_excel_attachment_batch(since_uid=cache.last_uid)
        if cache.uidvalidity and batch.uidvalidity and cache.uidvalidity != batch.uidvalidity:
            return self._scan_full_with_cache()

        new_result = self._parse_attachments(batch.attachments, batch.scanned_messages, scan_mode="incremental")
        result = ScanResult(
            rows=_merge_order_rows(cache.rows, new_result.rows),
            warnings=[*cache.warnings, *new_result.warnings],
            scanned_messages=cache.scanned_messages + batch.scanned_messages,
            parsed_attachments=cache.parsed_attachments + len(batch.attachments),
            scan_mode="incremental",
        )
        self._save_cache(batch, result, previous_cache=cache)
        return result

    def _parse_attachments(
        self,
        attachments: list[EmailAttachment],
        scanned_messages: int,
        scan_mode: str,
    ) -> ScanResult:
        rows = []
        warnings = []
        for attachment in attachments:
            parse_result = parse_excel_attachment(
                attachment.filename,
                attachment.content,
                self.aliases,
                message_subject=attachment.message_subject,
                message_date=attachment.message_date,
            )
            rows.extend(parse_result.rows)
            warnings.extend(parse_result.warnings)

        return ScanResult(
            rows=rows,
            warnings=warnings,
            scanned_messages=scanned_messages,
            parsed_attachments=len(attachments),
            scan_mode=scan_mode,
        )

    def scan_recent_orders(self, hours: int = 24) -> ScanResult:
        return self.scan_orders(hours=hours)

    def _cache_matches_account(self, cache: OrderCache) -> bool:
        return bool(cache.email and self.account_email and cache.email == self.account_email)

    def _save_cache(
        self,
        batch: AttachmentFetchResult,
        result: ScanResult,
        previous_cache: OrderCache | None = None,
    ) -> None:
        if self.cache_path is None:
            return

        uidvalidity = batch.uidvalidity or (previous_cache.uidvalidity if previous_cache else "")
        save_order_cache(
            OrderCache(
                email=self.account_email,
                uidvalidity=uidvalidity,
                last_uid=max(batch.latest_uid, previous_cache.last_uid if previous_cache else 0),
                rows=result.rows,
                warnings=result.warnings,
                scanned_messages=result.scanned_messages,
                parsed_attachments=result.parsed_attachments,
            ),
            self.cache_path,
        )


def _merge_order_rows(existing_rows: list[OrderRow], new_rows: list[OrderRow]) -> list[OrderRow]:
    merged: dict[str, OrderRow] = {}
    order_numbers: list[str] = []

    for row in [*existing_rows, *new_rows]:
        if row.order_number not in merged:
            order_numbers.append(row.order_number)
        merged[row.order_number] = row

    return [merged[order_number] for order_number in order_numbers]


def _has_legacy_rows_without_message_dates(rows: list[OrderRow]) -> bool:
    return any(row.message_date is None for row in rows)
