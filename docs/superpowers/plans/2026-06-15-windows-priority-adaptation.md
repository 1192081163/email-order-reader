# Windows Priority Adaptation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the desktop email order reader prioritize Windows behavior for settings storage, notifications, and packaging.

**Architecture:** Keep the PySide6 app structure intact. Move platform-specific settings path logic into `settings.py`, keep notification setup in `MainWindow`, and strengthen the Windows PyInstaller script without changing app runtime behavior.

**Tech Stack:** Python 3.12, PySide6, pytest, PyInstaller.

---

### Task 1: Windows Settings Path And Migration

**Files:**
- Modify: `src/email_order_reader/settings.py`
- Test: `tests/test_settings.py`

- [x] Add tests for `%APPDATA%\EmailOrderReader\settings.json`.
- [x] Add tests that legacy `~/.email-order-reader/settings.json` migrates to the Windows path when no new settings file exists.
- [x] Implement path selection and migration.
- [x] Run `pytest tests/test_settings.py -q`.

### Task 2: Windows Tray Notification Readiness

**Files:**
- Modify: `src/email_order_reader/ui/main_window.py`
- Test: `tests/test_main_window.py`

- [x] Add a test-friendly method that creates the tray icon once.
- [x] Call it at startup and before showing notifications.
- [x] Run `pytest tests/test_main_window.py -q`.

### Task 3: Windows Build Script

**Files:**
- Modify: `scripts/build_windows.ps1`
- Modify: `README.md`

- [x] Update the PowerShell script to create `.venv`, install package dev dependencies, run tests, and build with PyInstaller.
- [x] Document the Windows settings path and build output.
- [x] Run all tests.
