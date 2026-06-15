# Email Order Reader Design

## Goal

Build a minimal cross-platform desktop app that reads recent IMAP email attachments, extracts order data from Excel files, and shows the current scan result in a two-column table.

The app targets Windows and macOS with one Python codebase. Packaging is platform-specific: Windows builds produce an `.exe`, and macOS builds produce an `.app`.

## First Version Scope

The first version includes:

- Manual IMAP connection fields: server, port, email address, and authorization code.
- No credential persistence. Values exist only while the app process is running.
- Manual refresh action.
- Email scan window fixed to the latest 24 hours.
- Excel attachment parsing for `.xlsx`, `.xlsm`, and `.xls`.
- Automatic detection of the order number column and delivery-date column, with hidden advanced aliases for manual adjustment.
- Foreground table with exactly two visible data columns: `订单号` and `截至时间`.
- Status text for scan progress, errors, and attachments that cannot be parsed.

The first version does not include:

- Saved email accounts or saved authorization codes.
- Historical order storage.
- Export.
- Automatic background polling.
- Multi-account support.

## UI Design

The window has two main regions.

Top configuration region:

- `IMAP服务器`
- `端口` with `993` as the default SSL/TLS IMAP port
- `邮箱`
- `授权码`
- `刷新`

After all required connection fields are filled, the configuration region automatically collapses into a compact summary row. The compact row keeps:

- the email address or server summary,
- the `刷新` button,
- a `修改邮箱设置` action that expands the fields again.

This keeps the result table prominent while still allowing users to edit settings. The authorization code field is always password-masked, including before collapse. Collapse only changes what is visible; it does not write credentials to disk.

Main result region:

- A table with two visible columns:
  - `订单号`
  - `截至时间`
- A small status line below the table for messages such as:
  - `正在连接邮箱...`
  - `正在扫描最近24小时邮件...`
  - `已解析 3 个附件，读取 12 条订单`
  - `未识别列：filename.xlsx`

The UI should be plain and operational, not decorative. Use a simple native-feeling PySide6 layout with readable spacing and stable table columns.

## Email Flow

1. User fills IMAP server, port, email address, and authorization code.
2. App collapses the configuration region when all required fields are present.
3. User clicks `刷新`.
4. App connects to IMAP over SSL/TLS.
5. App searches the inbox for messages from the latest 24 hours.
6. App downloads Excel attachments from matching messages.
7. App parses each attachment and adds detected rows to the current result table.
8. Current results replace the previous scan results. Nothing is stored between app launches.

## Excel Parsing

The parser reads workbook sheets and attempts to detect the required columns.

Order number aliases include:

- `订单号`
- `订单编号`
- `客户订单号`
- `Order No`
- `Order Number`
- `PO`
- `PO Number`

Deadline aliases include:

- `交单日期`
- `截至时间`
- `截止时间`
- `交货日期`
- `Delivery Date`
- `Due Date`

The parser first uses header-name matching. If direct matching fails, it can use lightweight heuristics:

- likely order number columns contain repeated text-like IDs,
- likely date columns contain Excel dates or date-like strings,
- empty rows are skipped.

If a workbook cannot be parsed or a required column cannot be identified, the app reports that attachment in the status area and continues parsing other attachments.

Manual adjustment is available through a hidden advanced area behind `修改邮箱设置`. It contains two alias inputs:

- order number aliases,
- deadline aliases.

These aliases are used only for the current app session and are not shown in the main table.

## Error Handling

Expected errors should be shown in the status line without crashing the app:

- invalid IMAP server or port,
- login failure,
- network timeout,
- mailbox search failure,
- attachment download failure,
- unsupported attachment format,
- workbook parse error,
- missing order number or deadline column.

Failures for one email or attachment should not stop the entire scan unless the IMAP connection itself fails.

## Architecture

Suggested modules:

- `app.py`: application entry point.
- `ui/main_window.py`: PySide6 window, form collapse behavior, table rendering, status updates.
- `email_client.py`: IMAP connection, recent-message search, attachment extraction.
- `excel_parser.py`: workbook parsing and column detection.
- `models.py`: small dataclasses for scan results, attachment parse results, and order rows.

The UI should call email scanning in a worker thread so the window stays responsive during network and Excel operations.

## Testing

Use focused tests for the parts that can be tested without a real email account:

- Excel parser detects common Chinese and English column aliases.
- Excel parser handles Excel date cells and date strings.
- Excel parser skips empty rows.
- Excel parser reports missing columns cleanly.
- IMAP date-window calculation selects the latest 24 hours.

Manual verification covers:

- launching the desktop app,
- field completion and automatic collapse,
- expanding settings again,
- refresh button behavior,
- status display for failed login,
- status display for a successful scan using a test mailbox.

## Packaging

Use the same source code for Windows and macOS.

Build artifacts are created separately:

- Windows: PyInstaller `.exe`.
- macOS: PyInstaller `.app`.

Unsigned internal builds are acceptable for the first version, with the known tradeoff that Windows SmartScreen or macOS Gatekeeper may show warnings.
