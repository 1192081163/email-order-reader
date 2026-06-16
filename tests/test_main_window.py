from datetime import date, datetime, timezone

import pytest
from PySide6.QtCore import QDate
from PySide6.QtWidgets import QLabel, QMessageBox, QSystemTrayIcon

import email_order_reader.settings as settings_module
import email_order_reader.ui.main_window as main_window_module
from email_order_reader.models import OrderRow, ScanResult
from email_order_reader.updates import UpdateInfo
from email_order_reader.ui.main_window import DEFAULT_IMAP_PORT, DEFAULT_IMAP_SERVER, MainWindow


@pytest.fixture(autouse=True)
def isolate_default_settings_path(monkeypatch, tmp_path):
    monkeypatch.setattr(settings_module, "default_settings_path", lambda: tmp_path / "settings.json")
    monkeypatch.setattr(settings_module, "legacy_settings_path", lambda: tmp_path / "legacy" / "settings.json")


def test_settings_collapse_after_email_and_auth_code_are_filled(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)

    window.email_input.setText("buyer@example.com")
    window.auth_code_input.setText("secret")

    assert window.settings_panel.isHidden()
    assert not window.summary_panel.isHidden()
    assert "buyer@example.com" in window.summary_label.text()


def test_edit_settings_expands_inputs(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)

    window.email_input.setText("buyer@example.com")
    window.auth_code_input.setText("secret")
    window.edit_settings_button.click()

    assert not window.settings_panel.isHidden()
    assert window.summary_panel.isHidden()


def test_edit_settings_does_not_auto_collapse_while_typing(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)

    window.email_input.setText("buyer@example.com")
    window.auth_code_input.setText("secret")
    window.edit_settings_button.click()
    window.email_input.setText("changed@example.com")

    assert not window.settings_panel.isHidden()
    assert window.summary_panel.isHidden()


def test_save_settings_button_returns_to_summary(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)

    window.email_input.setText("buyer@example.com")
    window.auth_code_input.setText("secret")
    window.edit_settings_button.click()
    window.email_input.setText("changed@example.com")
    window.save_settings_button.click()

    assert window.settings_panel.isHidden()
    assert not window.summary_panel.isHidden()
    assert "changed@example.com" in window.summary_label.text()


def test_imap_server_and_port_are_hidden_enterprise_wechat_defaults(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)

    visible_labels = [label.text() for label in window.findChildren(QLabel) if not label.isHidden()]

    assert "IMAP服务器" not in visible_labels
    assert "端口" not in visible_labels


def test_build_config_uses_enterprise_wechat_defaults(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)

    window.email_input.setText("buyer@example.com")
    window.auth_code_input.setText("secret")
    config = window.build_config()

    assert config is not None
    assert config.server == DEFAULT_IMAP_SERVER
    assert config.port == DEFAULT_IMAP_PORT
    assert config.email == "buyer@example.com"
    assert config.auth_code == "secret"


def freeze_today(monkeypatch, year=2026, month=6, day=16):
    class FixedDate(date):
        @classmethod
        def today(cls):
            return cls(year, month, day)

    monkeypatch.setattr(main_window_module, "date", FixedDate)


def sent_datetime(day: int) -> datetime:
    return datetime(2026, 6, day, 9, 0, tzinfo=timezone.utc)


def test_manual_column_alias_controls_are_not_shown(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)

    visible_labels = [label.text() for label in window.findChildren(QLabel) if not label.isHidden()]

    assert not hasattr(window, "advanced_toggle_button")
    assert "高级列名" not in visible_labels
    assert "订单号别名" not in visible_labels
    assert "截至时间别名" not in visible_labels


def test_calendar_filter_controls_are_always_visible(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)

    assert hasattr(window, "filter_panel")
    assert not window.filter_panel.isHidden()
    assert window.order_search_input.placeholderText() == "搜索订单号"
    assert window.start_date_edit.calendarPopup()
    assert window.end_date_edit.calendarPopup()
    assert window.clear_date_filter_button.text() == "清空日期"
    assert window.check_update_button.text() == "检查更新"
    visible_labels = [label.text() for label in window.findChildren(QLabel) if not label.isHidden()]
    assert "发送时间" in visible_labels


def test_table_renders_all_order_rows_by_default(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)

    window.apply_scan_result(
        ScanResult(
            rows=[
                OrderRow(order_number="PO-7007", deadline="2026-06-16", message_date=sent_datetime(16)),
                OrderRow(order_number="PO-NEXT", deadline="2026-06-22", message_date=sent_datetime(22)),
            ],
            scanned_messages=1,
            parsed_attachments=1,
        )
    )

    assert window.table.rowCount() == 2
    assert window.table.item(0, 0).text() == "PO-7007"
    assert window.table.item(0, 1).text() == "2026-06-16"
    assert window.table.item(1, 0).text() == "PO-NEXT"
    assert "读取 2 条订单" in window.status_label.text()


def test_table_sorts_order_rows_by_deadline(qtbot, monkeypatch):
    freeze_today(monkeypatch)
    window = MainWindow()
    qtbot.addWidget(window)

    window.apply_scan_result(
        ScanResult(
            rows=[
                OrderRow(order_number="PO-LATE", deadline="2026-06-21", message_date=sent_datetime(16)),
                OrderRow(order_number="PO-EARLY", deadline="2026-06-15", message_date=sent_datetime(16)),
                OrderRow(order_number="PO-UNKNOWN", deadline="待确认"),
            ],
            scanned_messages=1,
            parsed_attachments=1,
        )
    )

    assert [window.table.item(row, 0).text() for row in range(window.table.rowCount())] == [
        "PO-EARLY",
        "PO-LATE",
        "PO-UNKNOWN",
    ]


def test_table_sorts_legacy_deadline_text_formats(qtbot, monkeypatch):
    freeze_today(monkeypatch)
    window = MainWindow()
    qtbot.addWidget(window)

    window.apply_scan_result(
        ScanResult(
            rows=[
                OrderRow(order_number="PO-SLASH", deadline="2026/6/20 00:00:00", message_date=sent_datetime(16)),
                OrderRow(order_number="PO-CHINESE", deadline="2026年6月18日 18:30", message_date=sent_datetime(16)),
                OrderRow(order_number="PO-UNKNOWN", deadline="待确认"),
            ],
            scanned_messages=1,
            parsed_attachments=1,
        )
    )

    assert [window.table.item(row, 0).text() for row in range(window.table.rowCount())] == [
        "PO-CHINESE",
        "PO-SLASH",
        "PO-UNKNOWN",
    ]


def test_table_sorts_deadlines_by_date_ascending(qtbot, monkeypatch):
    freeze_today(monkeypatch)
    window = MainWindow()
    qtbot.addWidget(window)

    window.apply_scan_result(
        ScanResult(
            rows=[
                OrderRow(order_number="29914", deadline="2026-06-15", message_date=sent_datetime(16)),
                OrderRow(order_number="29904", deadline="2026-06-16", message_date=sent_datetime(16)),
                OrderRow(order_number="29912", deadline="2026-06-16", message_date=sent_datetime(16)),
                OrderRow(order_number="29905", deadline="2026-06-17", message_date=sent_datetime(16)),
                OrderRow(order_number="29917", deadline="2026-06-18", message_date=sent_datetime(16)),
                OrderRow(order_number="29923", deadline="2026-06-18", message_date=sent_datetime(16)),
                OrderRow(order_number="29988", deadline="2026-06-20", message_date=sent_datetime(16)),
                OrderRow(order_number="29953", deadline="2026-06-21", message_date=sent_datetime(16)),
            ],
            scanned_messages=1,
            parsed_attachments=1,
        )
    )

    assert [window.table.item(row, 0).text() for row in range(window.table.rowCount())] == [
        "29914",
        "29904",
        "29912",
        "29905",
        "29917",
        "29923",
        "29988",
        "29953",
    ]


def test_calendar_filter_uses_email_sent_time_range(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)

    window.apply_scan_result(
        ScanResult(
            rows=[
                OrderRow(order_number="NEXT-WEEK", deadline="2026-06-22", message_date=sent_datetime(22)),
                OrderRow(order_number="WEEK-END", deadline="2026-06-21", message_date=sent_datetime(21)),
                OrderRow(order_number="TODAY", deadline="2026-06-16", message_date=sent_datetime(16)),
                OrderRow(order_number="WEEK-START", deadline="2026-06-15", message_date=sent_datetime(15)),
                OrderRow(order_number="PREV-WEEK", deadline="2026-06-14", message_date=sent_datetime(14)),
                OrderRow(order_number="UNKNOWN", deadline="待确认"),
            ],
            scanned_messages=1,
            parsed_attachments=1,
        )
    )

    window.start_date_edit.setDate(QDate(2026, 6, 15))
    window.end_date_edit.setDate(QDate(2026, 6, 21))

    assert [window.table.item(row, 0).text() for row in range(window.table.rowCount())] == [
        "WEEK-START",
        "TODAY",
        "WEEK-END",
    ]

    window.start_date_edit.setDate(QDate(2026, 6, 22))
    window.end_date_edit.setDate(QDate(2026, 6, 28))

    assert [window.table.item(row, 0).text() for row in range(window.table.rowCount())] == ["NEXT-WEEK"]

    window.clear_date_filter_button.click()

    assert [window.table.item(row, 0).text() for row in range(window.table.rowCount())] == [
        "PREV-WEEK",
        "WEEK-START",
        "TODAY",
        "WEEK-END",
        "NEXT-WEEK",
        "UNKNOWN",
    ]


def test_calendar_filter_uses_email_sent_time_instead_of_deadline(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)

    window.apply_scan_result(
        ScanResult(
            rows=[
                OrderRow(order_number="SENT-THIS-WEEK", deadline="2026-07-10", message_date=sent_datetime(16)),
                OrderRow(order_number="DEADLINE-THIS-WEEK", deadline="2026-06-16", message_date=sent_datetime(22)),
            ],
            scanned_messages=2,
            parsed_attachments=2,
        )
    )

    window.start_date_edit.setDate(QDate(2026, 6, 15))
    window.end_date_edit.setDate(QDate(2026, 6, 21))

    assert [window.table.item(row, 0).text() for row in range(window.table.rowCount())] == ["SENT-THIS-WEEK"]


def test_order_search_filters_order_numbers_with_date_range(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)

    window.apply_scan_result(
        ScanResult(
            rows=[
                OrderRow(order_number="PO-1001", deadline="2026-06-15", message_date=sent_datetime(16)),
                OrderRow(order_number="PO-2002", deadline="2026-06-16", message_date=sent_datetime(16)),
                OrderRow(order_number="AX-2002", deadline="2026-06-17", message_date=sent_datetime(22)),
            ],
            scanned_messages=3,
            parsed_attachments=3,
        )
    )

    window.start_date_edit.setDate(QDate(2026, 6, 15))
    window.end_date_edit.setDate(QDate(2026, 6, 21))
    window.order_search_input.setText("2002")

    assert [window.table.item(row, 0).text() for row in range(window.table.rowCount())] == ["PO-2002"]


def test_first_scan_sets_baseline_without_order_change_notification(qtbot, monkeypatch):
    window = MainWindow()
    qtbot.addWidget(window)
    notifications = []
    monkeypatch.setattr(window, "notify_order_changes", lambda new_count, updated_count: notifications.append((new_count, updated_count)))

    window.apply_scan_result(
        ScanResult(
            rows=[OrderRow(order_number="PO-1001", deadline="2026-06-20", message_date=sent_datetime(16))],
            scanned_messages=1,
            parsed_attachments=1,
        )
    )

    assert notifications == []
    assert window.highlighted_order_numbers == set()


def test_later_scan_notifies_new_and_updated_orders(qtbot, monkeypatch):
    freeze_today(monkeypatch)
    window = MainWindow()
    qtbot.addWidget(window)
    notifications = []
    monkeypatch.setattr(window, "notify_order_changes", lambda new_count, updated_count: notifications.append((new_count, updated_count)))
    window.apply_scan_result(
        ScanResult(
            rows=[OrderRow(order_number="PO-1001", deadline="2026-06-20", message_date=sent_datetime(16))],
            scanned_messages=1,
            parsed_attachments=1,
        )
    )

    window.apply_scan_result(
        ScanResult(
            rows=[
                OrderRow(order_number="PO-1001", deadline="2026-06-21", message_date=sent_datetime(16)),
                OrderRow(order_number="PO-2002", deadline="2026-06-19", message_date=sent_datetime(16)),
            ],
            scanned_messages=1,
            parsed_attachments=1,
        )
    )

    assert notifications == [(1, 1)]
    assert window.highlighted_order_numbers == {"PO-1001", "PO-2002"}
    assert [window.table.item(row, 0).text() for row in range(window.table.rowCount())] == [
        "PO-2002",
        "PO-1001",
    ]


def test_auto_refresh_timer_starts_after_saved_credentials_load(qtbot, tmp_path):
    settings_path = tmp_path / "settings.json"
    settings_path.write_text('{"email": "saved@example.com", "auth_code": "saved-secret"}', encoding="utf-8")

    window = MainWindow(settings_path=settings_path)
    qtbot.addWidget(window)

    assert window.auto_refresh_timer.isActive()
    assert window.auto_refresh_timer.interval() == 30_000
    assert "自动刷新" in window.status_label.text()


def test_auto_scan_skips_when_scan_is_running(qtbot, monkeypatch):
    window = MainWindow()
    qtbot.addWidget(window)
    window.email_input.setText("buyer@example.com")
    window.auth_code_input.setText("secret")
    calls = []
    monkeypatch.setattr(window, "start_scan", lambda auto=False: calls.append(auto))
    window.thread = object()

    window.start_auto_scan()

    assert calls == []


def test_window_prepares_system_tray_icon_when_available(qtbot, monkeypatch):
    monkeypatch.setattr(QSystemTrayIcon, "isSystemTrayAvailable", staticmethod(lambda: True))

    window = MainWindow()
    qtbot.addWidget(window)

    assert window.tray_icon is not None
    assert window.tray_icon.isVisible()


def test_scan_button_reads_all_inbox_messages(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)

    assert window.refresh_button.text() == "扫描全部邮件"


def test_scan_status_reports_no_inbox_messages(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)

    window.apply_scan_result(ScanResult(scanned_messages=0, parsed_attachments=0))

    assert "扫描到 0 封邮件" in window.status_label.text()
    assert "收件箱没有可扫描邮件" in window.status_label.text()
    assert "最近24小时" not in window.status_label.text()


def test_scan_status_reports_no_excel_attachments(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)

    window.apply_scan_result(ScanResult(scanned_messages=3, parsed_attachments=0))

    assert "扫描到 3 封邮件" in window.status_label.text()
    assert "没有找到 .xlsx/.xlsm/.xls 附件" in window.status_label.text()


def test_scan_status_reports_unparsed_excel_attachments(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)

    window.apply_scan_result(
        ScanResult(
            warnings=["orders.xlsx：未识别订单号列或截至时间列"],
            scanned_messages=2,
            parsed_attachments=1,
        )
    )

    assert "找到 1 个 Excel 附件" in window.status_label.text()
    assert "没有识别出订单号和截至时间" in window.status_label.text()
    assert "orders.xlsx：未识别订单号列或截至时间列" in window.status_label.text()


def test_login_failure_stops_auto_refresh(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    window.email_input.setText("buyer@example.com")
    window.auth_code_input.setText("secret")

    assert window.auto_refresh_timer.isActive()

    window.apply_scan_error("邮箱登录失败：请检查授权码。")

    assert not window.auto_refresh_timer.isActive()
    assert "扫描失败：邮箱登录失败" in window.status_label.text()
    assert "已暂停自动刷新" in window.status_label.text()


def test_window_loads_saved_credentials_and_collapses_settings(qtbot, tmp_path):
    settings_path = tmp_path / "settings.json"
    settings_path.write_text('{"email": "saved@example.com", "auth_code": "saved-secret"}', encoding="utf-8")

    window = MainWindow(settings_path=settings_path)
    qtbot.addWidget(window)

    assert window.email_input.text() == "saved@example.com"
    assert window.auth_code_input.text() == "saved-secret"
    assert window.settings_panel.isHidden()
    assert not window.summary_panel.isHidden()
    assert "已加载保存的邮箱" in window.status_label.text()


def test_window_saves_credentials_after_required_fields_are_filled(qtbot, tmp_path):
    settings_path = tmp_path / "settings.json"
    window = MainWindow(settings_path=settings_path)
    qtbot.addWidget(window)

    window.email_input.setText("buyer@example.com")
    window.auth_code_input.setText("secret")

    assert settings_path.read_text(encoding="utf-8") == (
        '{\n'
        '  "email": "buyer@example.com",\n'
        '  "auth_code": "secret"\n'
        '}'
    )


def test_window_prompts_to_download_new_update(qtbot, monkeypatch):
    window = MainWindow(check_updates_on_start=False)
    qtbot.addWidget(window)
    update = UpdateInfo(
        tag_name="build-15",
        release_url="https://github.com/1192081163/email-order-reader/releases/tag/build-15",
        asset_name="EmailOrderReader.exe",
        asset_url="https://example.com/EmailOrderReader.exe",
    )
    downloads = []

    monkeypatch.setattr(
        main_window_module.QMessageBox,
        "question",
        lambda *args, **kwargs: QMessageBox.StandardButton.Yes,
    )
    monkeypatch.setattr(window, "start_update_download", lambda update_info: downloads.append(update_info))

    window.handle_update_check_result(update)

    assert downloads == [update]


def test_manual_update_check_reports_current_version_when_no_update(qtbot, monkeypatch):
    window = MainWindow(check_updates_on_start=False)
    qtbot.addWidget(window)
    messages = []

    monkeypatch.setattr(
        main_window_module.QMessageBox,
        "information",
        lambda _parent, title, message: messages.append((title, message)),
    )

    window.manual_update_check_requested = True
    window.handle_update_check_result(None)

    assert messages == [("检查更新", "当前已是最新版本。")]
    assert not window.manual_update_check_requested


def test_manual_update_check_reports_failures(qtbot, monkeypatch):
    window = MainWindow(check_updates_on_start=False)
    qtbot.addWidget(window)
    messages = []

    monkeypatch.setattr(
        main_window_module.QMessageBox,
        "warning",
        lambda _parent, title, message: messages.append((title, message)),
    )

    window.manual_update_check_requested = True
    window.handle_update_check_error("network unavailable")

    assert messages == [("检查更新失败", "检查更新失败，不影响订单读取。")]
    assert not window.manual_update_check_requested


def test_window_opens_release_page_when_update_asset_is_missing(qtbot, monkeypatch):
    window = MainWindow(check_updates_on_start=False)
    qtbot.addWidget(window)
    update = UpdateInfo(
        tag_name="build-16",
        release_url="https://github.com/1192081163/email-order-reader/releases/tag/build-16",
        asset_name="",
        asset_url="",
    )
    opened_urls = []

    monkeypatch.setattr(
        main_window_module.QMessageBox,
        "question",
        lambda *args, **kwargs: QMessageBox.StandardButton.Yes,
    )
    monkeypatch.setattr(main_window_module.QDesktopServices, "openUrl", lambda url: opened_urls.append(url.toString()) or True)

    window.handle_update_check_result(update)

    assert opened_urls == [update.release_url]


def test_window_ignores_update_check_failures(qtbot):
    window = MainWindow(check_updates_on_start=False)
    qtbot.addWidget(window)
    original_status = window.status_label.text()

    window.handle_update_check_error("network unavailable")

    assert window.status_label.text() == original_status


def test_window_opens_downloaded_update_file(qtbot, monkeypatch, tmp_path):
    window = MainWindow(check_updates_on_start=False)
    qtbot.addWidget(window)
    download_path = tmp_path / "EmailOrderReader.exe"
    download_path.write_bytes(b"fake exe")
    opened_files = []

    monkeypatch.setattr(main_window_module.QDesktopServices, "openUrl", lambda url: opened_files.append(url.toLocalFile()) or True)

    window.handle_update_download_finished(download_path)

    assert opened_files == [str(download_path)]
    assert "新版已下载" in window.status_label.text()
