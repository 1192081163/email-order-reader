from PySide6.QtWidgets import QLabel

from email_order_reader.models import OrderRow, ScanResult
from email_order_reader.ui.main_window import DEFAULT_IMAP_PORT, DEFAULT_IMAP_SERVER, MainWindow


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


def test_hidden_alias_controls_build_session_aliases(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)

    assert window.advanced_panel.isHidden()

    window.advanced_toggle_button.click()
    window.order_alias_input.setText("编号, 采购单号")
    window.deadline_alias_input.setText("时间, 最晚日期")
    aliases = window.build_aliases()

    assert "编号" in aliases.order_number
    assert "采购单号" in aliases.order_number
    assert "时间" in aliases.deadline
    assert "最晚日期" in aliases.deadline


def test_table_renders_order_rows(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)

    window.apply_scan_result(
        ScanResult(
            rows=[OrderRow(order_number="PO-7007", deadline="2026-11-02")],
            scanned_messages=1,
            parsed_attachments=1,
        )
    )

    assert window.table.rowCount() == 1
    assert window.table.item(0, 0).text() == "PO-7007"
    assert window.table.item(0, 1).text() == "2026-11-02"
    assert "读取 1 条订单" in window.status_label.text()
