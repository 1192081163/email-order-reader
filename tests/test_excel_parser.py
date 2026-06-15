from datetime import date, datetime
from io import BytesIO

from openpyxl import Workbook

from email_order_reader.excel_parser import parse_excel_attachment
from email_order_reader.models import ColumnAliases


def make_xlsx(headers, rows, suffix="xlsx"):
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Orders"
    sheet.append(headers)
    for row in rows:
        sheet.append(row)

    stream = BytesIO()
    workbook.save(stream)
    return f"orders.{suffix}", stream.getvalue()


def test_parse_xlsx_with_chinese_headers():
    filename, content = make_xlsx(
        ["订单号", "交单日期", "备注"],
        [["PO-1001", date(2026, 6, 20), "加急"]],
    )

    result = parse_excel_attachment(filename, content, ColumnAliases.default())

    assert result.warnings == []
    assert [(row.order_number, row.deadline) for row in result.rows] == [("PO-1001", "2026-06-20")]


def test_parse_xlsm_with_english_headers_and_datetime_cell():
    filename, content = make_xlsx(
        ["Order Number", "Due Date"],
        [["PO-2002", datetime(2026, 7, 3, 9, 15)]],
        suffix="xlsm",
    )

    result = parse_excel_attachment(filename, content, ColumnAliases.default())

    assert result.warnings == []
    assert [(row.order_number, row.deadline) for row in result.rows] == [("PO-2002", "2026-07-03")]


def test_parse_skips_empty_order_rows():
    filename, content = make_xlsx(
        ["订单编号", "截止时间"],
        [[None, date(2026, 6, 20)], ["PO-3003", "2026/06/21"]],
    )

    result = parse_excel_attachment(filename, content, ColumnAliases.default())

    assert result.warnings == []
    assert [(row.order_number, row.deadline) for row in result.rows] == [("PO-3003", "2026-06-21")]


def test_parse_reports_missing_columns():
    filename, content = make_xlsx(
        ["客户", "金额"],
        [["ACME", 100]],
    )

    result = parse_excel_attachment(filename, content, ColumnAliases.default())

    assert result.rows == []
    assert result.warnings == ["orders.xlsx：未识别订单号列或截至时间列"]
