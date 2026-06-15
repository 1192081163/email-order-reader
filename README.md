# Email Order Reader

Minimal desktop app for scanning recent IMAP email attachments and showing order deadlines.

## Behavior

- Scans the inbox for email from the latest 24 hours.
- Uses Enterprise WeChat/Tencent Exmail IMAP defaults internally: `imap.exmail.qq.com:993`.
- Reads Excel attachments with `.xlsx`, `.xlsm`, or `.xls` extensions.
- Shows only two columns: `订单号` and `截至时间`.
- Shows only email address and authorization code in the mailbox settings area, then collapses it after both are filled.
- Does not save mailbox credentials.
- Does not save scan history.

## Development

Use Python 3.11 or newer.

```bash
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
python -m pytest
```

## Run

```bash
email-order-reader
```

## Package

macOS:

```bash
bash scripts/build_macos.sh
```

Windows PowerShell:

```powershell
.\scripts\build_windows.ps1
```

Unsigned internal builds may show Windows SmartScreen or macOS Gatekeeper warnings.
