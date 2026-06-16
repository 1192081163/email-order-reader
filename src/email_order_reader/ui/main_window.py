from __future__ import annotations

import re
from datetime import date, datetime, timedelta
from pathlib import Path

from PySide6.QtCore import QObject, QThread, QTimer, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QStyle,
    QSystemTrayIcon,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

import email_order_reader.settings as settings_module
from email_order_reader.email_client import ImapEmailClient
from email_order_reader.models import ImapConfig, ScanResult
from email_order_reader.scan_service import OrderScanService
from email_order_reader.settings import AppSettings, load_settings, save_settings


DEFAULT_IMAP_SERVER = "imap.exmail.qq.com"
DEFAULT_IMAP_PORT = 993
AUTO_REFRESH_INTERVAL_MS = 30_000
HIGHLIGHT_COLOR = QColor("#fff3a3")


class ScanWorker(QObject):
    finished = Signal(object)
    failed = Signal(str)

    def __init__(self, config: ImapConfig, cache_path: Path, full_scan: bool) -> None:
        super().__init__()
        self.config = config
        self.cache_path = cache_path
        self.full_scan = full_scan

    def run(self) -> None:
        try:
            client = ImapEmailClient(self.config)
            service = OrderScanService(
                client=client,
                cache_path=self.cache_path,
                account_email=self.config.email,
            )
            self.finished.emit(service.scan_orders(full_scan=self.full_scan))
        except Exception as exc:
            self.failed.emit(str(exc))


class MainWindow(QMainWindow):
    def __init__(self, settings_path: Path | None = None) -> None:
        super().__init__()
        self.setWindowTitle("邮件订单读取")
        self.resize(760, 520)
        self.thread: QThread | None = None
        self.worker: ScanWorker | None = None
        self.settings_path = settings_path
        self.order_cache_path = _order_cache_path(settings_path)
        self._loading_settings = True
        self.editing_settings = False
        self.seen_orders: dict[str, str] = {}
        self.order_rows: list = []
        self.has_scan_baseline = False
        self.highlighted_order_numbers: set[str] = set()
        self.week_offset = 0
        self.last_scan_result: ScanResult | None = None
        self.tray_icon: QSystemTrayIcon | None = None
        self.auto_refresh_timer = QTimer(self)
        self.auto_refresh_timer.setInterval(AUTO_REFRESH_INTERVAL_MS)
        self.auto_refresh_timer.timeout.connect(self.start_auto_scan)

        root = QWidget()
        root.setObjectName("root")
        self.setCentralWidget(root)
        self.root_layout = QVBoxLayout(root)
        self.root_layout.setContentsMargins(18, 18, 18, 14)
        self.root_layout.setSpacing(12)

        self.settings_panel = QWidget()
        self.settings_panel.setObjectName("settingsPanel")
        settings_layout = QFormLayout(self.settings_panel)
        settings_layout.setContentsMargins(16, 14, 16, 14)
        settings_layout.setHorizontalSpacing(12)
        settings_layout.setVerticalSpacing(10)
        self.email_input = QLineEdit()
        self.auth_code_input = QLineEdit()
        self.auth_code_input.setEchoMode(QLineEdit.Password)

        settings_layout.addRow("邮箱", self.email_input)
        settings_layout.addRow("授权码", self.auth_code_input)

        settings_button_row = QHBoxLayout()
        settings_button_row.addStretch()
        self.save_settings_button = QPushButton("保存并返回")
        self.save_settings_button.setProperty("kind", "secondary")
        self.refresh_button = QPushButton("扫描全部邮件")
        self.refresh_button.setProperty("kind", "primary")
        settings_button_row.addWidget(self.save_settings_button)
        settings_button_row.addWidget(self.refresh_button)
        settings_layout.addRow(settings_button_row)

        self.summary_panel = QWidget()
        self.summary_panel.setObjectName("toolbar")
        summary_layout = QHBoxLayout(self.summary_panel)
        summary_layout.setContentsMargins(14, 10, 14, 10)
        summary_layout.setSpacing(10)
        self.summary_label = QLabel("")
        self.summary_label.setObjectName("summaryLabel")
        self.summary_refresh_button = QPushButton("刷新")
        self.summary_refresh_button.setProperty("kind", "primary")
        self.edit_settings_button = QPushButton("修改邮箱设置")
        self.edit_settings_button.setProperty("kind", "secondary")
        summary_layout.addWidget(self.summary_label)
        summary_layout.addStretch()
        summary_layout.addWidget(self.summary_refresh_button)
        summary_layout.addWidget(self.edit_settings_button)
        self.summary_panel.hide()

        self.filter_panel = QWidget()
        self.filter_panel.setObjectName("filterPanel")
        filter_layout = QHBoxLayout(self.filter_panel)
        filter_layout.setContentsMargins(14, 8, 14, 8)
        filter_layout.setSpacing(8)
        filter_label = QLabel("截止周")
        self.previous_week_button = QPushButton("上周")
        self.previous_week_button.setProperty("kind", "secondary")
        self.current_week_button = QPushButton("本周")
        self.current_week_button.setProperty("kind", "primary")
        self.next_week_button = QPushButton("下周")
        self.next_week_button.setProperty("kind", "secondary")
        self.week_label = QLabel("")
        self.week_label.setObjectName("weekLabel")
        filter_layout.addWidget(filter_label)
        filter_layout.addWidget(self.previous_week_button)
        filter_layout.addWidget(self.current_week_button)
        filter_layout.addWidget(self.next_week_button)
        filter_layout.addWidget(self.week_label)
        filter_layout.addStretch()

        self.table = QTableWidget(0, 2)
        self.table.setObjectName("ordersTable")
        self.table.setHorizontalHeaderLabels(["订单号", "截至时间"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.verticalHeader().setVisible(False)
        self.table.setAlternatingRowColors(True)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setShowGrid(False)

        self.status_label = QLabel("请填写邮箱信息后刷新。")
        self.status_label.setObjectName("statusLabel")
        self.status_label.setWordWrap(True)

        self.root_layout.addWidget(self.settings_panel)
        self.root_layout.addWidget(self.summary_panel)
        self.root_layout.addWidget(self.filter_panel)
        self.root_layout.addWidget(self.table)
        self.root_layout.addWidget(self.status_label)

        for input_widget in (self.email_input, self.auth_code_input):
            input_widget.textChanged.connect(self.update_settings_visibility)
        self.edit_settings_button.clicked.connect(self.expand_settings)
        self.save_settings_button.clicked.connect(self.finish_editing_settings)
        self.refresh_button.clicked.connect(lambda: self.start_scan(full_scan=True))
        self.summary_refresh_button.clicked.connect(lambda: self.start_scan(full_scan=False))
        self.previous_week_button.clicked.connect(self.show_previous_week)
        self.current_week_button.clicked.connect(self.show_current_week)
        self.next_week_button.clicked.connect(self.show_next_week)

        self.apply_style()
        self.load_saved_settings()
        self._loading_settings = False
        self.ensure_tray_icon()
        self.update_week_label()
        self.update_settings_visibility()

    def required_fields_present(self) -> bool:
        return all(
            field.text().strip()
            for field in (self.email_input, self.auth_code_input)
        )

    def update_settings_visibility(self) -> None:
        if self.required_fields_present():
            self.save_current_settings()
            if not self.editing_settings:
                self.collapse_settings()
            self.start_auto_refresh()
        else:
            self.stop_auto_refresh()

    def collapse_settings(self) -> None:
        self.editing_settings = False
        self.summary_label.setText(self.email_input.text().strip())
        self.settings_panel.hide()
        self.summary_panel.show()
        if self.status_label.text() == "请填写邮箱信息后刷新。":
            self.status_label.setText("已加载保存的邮箱，自动刷新中。")

    def expand_settings(self) -> None:
        self.editing_settings = True
        self.summary_panel.hide()
        self.settings_panel.show()

    def finish_editing_settings(self) -> None:
        if not self.required_fields_present():
            QMessageBox.warning(self, "缺少邮箱信息", "请填写邮箱和授权码。")
            return

        self.editing_settings = False
        self.save_current_settings()
        self.collapse_settings()
        self.start_auto_refresh()

    def build_config(self) -> ImapConfig | None:
        if not self.required_fields_present():
            QMessageBox.warning(self, "缺少邮箱信息", "请填写邮箱和授权码。")
            return None
        return ImapConfig(
            server=DEFAULT_IMAP_SERVER,
            port=DEFAULT_IMAP_PORT,
            email=self.email_input.text().strip(),
            auth_code=self.auth_code_input.text(),
        )

    def load_saved_settings(self) -> None:
        settings = load_settings(self.settings_path)
        self.email_input.setText(settings.email)
        self.auth_code_input.setText(settings.auth_code)

    def save_current_settings(self) -> None:
        if self._loading_settings:
            return
        save_settings(
            AppSettings(
                email=self.email_input.text().strip(),
                auth_code=self.auth_code_input.text(),
            ),
            self.settings_path,
        )

    def start_auto_refresh(self) -> None:
        if not self.auto_refresh_timer.isActive():
            self.auto_refresh_timer.start()

    def stop_auto_refresh(self) -> None:
        if self.auto_refresh_timer.isActive():
            self.auto_refresh_timer.stop()

    def start_auto_scan(self) -> None:
        if self.thread is not None or not self.required_fields_present():
            return
        self.start_scan(auto=True, full_scan=False)

    def start_scan(self, auto: bool = False, full_scan: bool = False) -> None:
        config = self.build_config()
        if config is None:
            return

        self.refresh_button.setEnabled(False)
        self.summary_refresh_button.setEnabled(False)
        if full_scan:
            status = "正在扫描全部邮件..."
        elif auto:
            status = "自动刷新新邮件..."
        else:
            status = "正在刷新新邮件..."
        self.status_label.setText(status)

        self.thread = QThread()
        self.worker = ScanWorker(config=config, cache_path=self.order_cache_path, full_scan=full_scan)
        self.worker.moveToThread(self.thread)
        self.thread.started.connect(self.worker.run)
        self.worker.finished.connect(self.apply_scan_result)
        self.worker.failed.connect(self.apply_scan_error)
        self.worker.finished.connect(self.thread.quit)
        self.worker.failed.connect(self.thread.quit)
        self.worker.finished.connect(self.worker.deleteLater)
        self.worker.failed.connect(self.worker.deleteLater)
        self.thread.finished.connect(self.thread.deleteLater)
        self.thread.finished.connect(self._scan_finished)
        self.thread.start()

    def _scan_finished(self) -> None:
        self.refresh_button.setEnabled(True)
        self.summary_refresh_button.setEnabled(True)
        self.thread = None
        self.worker = None

    def apply_scan_result(self, result: ScanResult) -> None:
        self.last_scan_result = result
        self.order_rows = _sorted_order_rows(result.rows)
        self.highlighted_order_numbers = self.detect_order_changes(self.order_rows)
        displayed_count = self.render_order_rows()
        self.status_label.setText(
            _format_scan_status(
                result,
                auto_refreshing=self.auto_refresh_timer.isActive(),
                displayed_row_count=displayed_count,
            )
        )

    def render_order_rows(self) -> int:
        self.update_week_label()
        display_rows = _filter_order_rows_for_week(self.order_rows, self.week_offset)
        self.table.setRowCount(0)
        for row in display_rows:
            row_index = self.table.rowCount()
            self.table.insertRow(row_index)
            order_item = QTableWidgetItem(row.order_number)
            deadline_item = QTableWidgetItem(row.deadline)
            if row.order_number in self.highlighted_order_numbers:
                order_item.setBackground(HIGHLIGHT_COLOR)
                deadline_item.setBackground(HIGHLIGHT_COLOR)
            self.table.setItem(row_index, 0, order_item)
            self.table.setItem(row_index, 1, deadline_item)
        return len(display_rows)

    def show_previous_week(self) -> None:
        self.week_offset -= 1
        self.refresh_week_view()

    def show_current_week(self) -> None:
        self.week_offset = 0
        self.refresh_week_view()

    def show_next_week(self) -> None:
        self.week_offset += 1
        self.refresh_week_view()

    def refresh_week_view(self) -> None:
        displayed_count = self.render_order_rows()
        if self.last_scan_result is not None:
            self.status_label.setText(
                _format_scan_status(
                    self.last_scan_result,
                    auto_refreshing=self.auto_refresh_timer.isActive(),
                    displayed_row_count=displayed_count,
                )
            )

    def update_week_label(self) -> None:
        week_start, week_end = _week_range(self.week_offset)
        self.week_label.setText(f"{week_start.isoformat()} 至 {week_end.isoformat()}")

    def apply_scan_error(self, message: str) -> None:
        if "邮箱登录失败" in message:
            self.stop_auto_refresh()
            self.status_label.setText(f"扫描失败：{message} 已暂停自动刷新。")
            return

        self.status_label.setText(f"扫描失败：{message}")

    def detect_order_changes(self, rows: list) -> set[str]:
        current_orders = {row.order_number: row.deadline for row in rows}
        if not self.has_scan_baseline:
            self.seen_orders = current_orders
            self.has_scan_baseline = True
            return set()

        new_orders = set(current_orders) - set(self.seen_orders)
        updated_orders = {
            order_number
            for order_number, deadline in current_orders.items()
            if order_number in self.seen_orders and self.seen_orders[order_number] != deadline
        }
        self.seen_orders = current_orders

        if new_orders or updated_orders:
            self.notify_order_changes(len(new_orders), len(updated_orders))

        return new_orders | updated_orders

    def notify_order_changes(self, new_count: int, updated_count: int) -> None:
        message_parts = []
        if new_count:
            message_parts.append(f"新增 {new_count} 条订单")
        if updated_count:
            message_parts.append(f"更新 {updated_count} 条订单")
        message = "，".join(message_parts)
        if not message:
            return

        QApplication.alert(self, 0)
        self.ensure_tray_icon()
        if self.tray_icon is not None:
            self.tray_icon.showMessage("邮件订单更新", message, QSystemTrayIcon.MessageIcon.Information, 5000)

    def ensure_tray_icon(self) -> None:
        if self.tray_icon is not None or not QSystemTrayIcon.isSystemTrayAvailable():
            return

        icon = self.style().standardIcon(QStyle.StandardPixmap.SP_MessageBoxInformation)
        self.tray_icon = QSystemTrayIcon(icon, self)
        self.tray_icon.setToolTip("邮件订单读取")
        self.tray_icon.show()

    def apply_style(self) -> None:
        self.setStyleSheet(
            """
            QWidget#root {
                background: #f6f7f9;
                color: #1f2937;
                font-size: 13px;
            }

            QWidget#settingsPanel, QWidget#toolbar, QWidget#filterPanel {
                background: #ffffff;
                border: 1px solid #d8dde6;
                border-radius: 8px;
            }

            QLabel#summaryLabel {
                color: #111827;
                font-weight: 600;
            }

            QLineEdit {
                background: #ffffff;
                border: 1px solid #cfd6e0;
                border-radius: 6px;
                padding: 7px 9px;
                min-height: 22px;
                selection-background-color: #2563eb;
            }

            QLineEdit:focus {
                border-color: #2563eb;
            }

            QPushButton {
                border: 1px solid #cfd6e0;
                border-radius: 6px;
                padding: 7px 13px;
                background: #ffffff;
                color: #1f2937;
                min-height: 22px;
            }

            QPushButton:hover {
                background: #f2f5f9;
                border-color: #b8c2d0;
            }

            QPushButton:disabled {
                color: #9aa3af;
                background: #eef1f5;
            }

            QPushButton[kind="primary"] {
                background: #2563eb;
                border-color: #2563eb;
                color: #ffffff;
                font-weight: 600;
            }

            QPushButton[kind="primary"]:hover {
                background: #1d4ed8;
                border-color: #1d4ed8;
            }

            QPushButton[kind="secondary"] {
                background: #f8fafc;
            }

            QTableWidget#ordersTable {
                background: #ffffff;
                alternate-background-color: #f8fafc;
                border: 1px solid #d8dde6;
                border-radius: 8px;
                gridline-color: transparent;
                selection-background-color: #dbeafe;
                selection-color: #111827;
            }

            QTableWidget#ordersTable::item {
                padding: 8px;
                border-bottom: 1px solid #edf0f4;
            }

            QHeaderView::section {
                background: #eef2f7;
                color: #374151;
                padding: 9px 8px;
                border: 0;
                border-bottom: 1px solid #d8dde6;
                font-weight: 600;
            }

            QLabel#statusLabel {
                background: #ffffff;
                border: 1px solid #d8dde6;
                border-radius: 8px;
                padding: 10px 12px;
                color: #4b5563;
            }
            """
        )


def _format_scan_status(
    result: ScanResult,
    auto_refreshing: bool = False,
    displayed_row_count: int | None = None,
) -> str:
    scanned_label = "当前已处理" if result.scan_mode == "incremental" else "扫描到"
    row_count = result.row_count if displayed_row_count is None else displayed_row_count
    status = (
        f"{scanned_label} {result.scanned_messages} 封邮件，"
        f"找到 {result.parsed_attachments} 个 Excel 附件，"
        f"读取 {row_count} 条订单。"
    )

    details: list[str] = []
    if result.scanned_messages == 0:
        details.append("收件箱没有可扫描邮件；请确认订单邮件在收件箱")
    elif result.parsed_attachments == 0:
        details.append("这些邮件里没有找到 .xlsx/.xlsm/.xls 附件")
    elif result.row_count == 0:
        details.append("已找到附件，但没有识别出订单号和截至时间；请检查附件格式是否为支持的订单模板")
    elif displayed_row_count is not None and displayed_row_count == 0:
        details.append("当前选择的周没有订单")

    details.extend(result.warnings)
    if details:
        status = f"{status} {'；'.join(details)}"

    if auto_refreshing:
        status = f"{status} 自动刷新中，最后刷新时间 {datetime.now().strftime('%H:%M:%S')}。"

    return status


def _sorted_order_rows(rows: list) -> list:
    return sorted(rows, key=_order_row_sort_key)


def _order_row_sort_key(row) -> tuple:
    deadline = _parse_deadline_date(row.deadline)
    if deadline is None:
        return (1, datetime.max.date(), row.deadline, row.order_number)

    return (0, deadline, row.order_number)


def _filter_order_rows_for_week(rows: list, week_offset: int) -> list:
    week_start, week_end = _week_range(week_offset)
    return [
        row
        for row in rows
        if (deadline := _parse_deadline_date(row.deadline)) is not None and week_start <= deadline <= week_end
    ]


def _week_range(week_offset: int) -> tuple[date, date]:
    today = date.today()
    week_start = today - timedelta(days=today.weekday()) + timedelta(days=week_offset * 7)
    return week_start, week_start + timedelta(days=6)


def _parse_deadline_date(value: str) -> date | None:
    text = str(value).strip()
    patterns = (
        r"^\s*(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})(?:\s+\d{1,2}:\d{2}(?::\d{2})?)?\s*$",
        r"^\s*(\d{4})年\s*(\d{1,2})月\s*(\d{1,2})日(?:\s*\d{1,2}:\d{2}(?::\d{2})?)?\s*$",
    )
    for pattern in patterns:
        match = re.match(pattern, text)
        if not match:
            continue
        try:
            return date(*(int(part) for part in match.groups()))
        except ValueError:
            return None
    return None


def _order_cache_path(settings_path: Path | None) -> Path:
    if settings_path is not None:
        return settings_path.with_name("order_cache.json")
    return settings_module.default_settings_path().with_name("order_cache.json")
