import "@testing-library/jest-dom/vitest";
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { App } from "../../electron/renderer/App";
import type { RendererApi, ScanResult } from "../../electron/shared/types";

const emptyScanResult: ScanResult = {
  rows: [],
  warnings: [],
  scannedMessages: 0,
  parsedAttachments: 0,
  scanMode: "incremental",
};

const api: RendererApi = {
  loadSettings: vi.fn(),
  saveSettings: vi.fn(),
  scanOrders: vi.fn(),
  checkUpdates: vi.fn(),
  downloadUpdate: vi.fn(),
  installUpdate: vi.fn(),
};

beforeEach(() => {
  vi.resetAllMocks();
  vi.mocked(api.loadSettings).mockResolvedValue({ email: "", authCode: "" });
  vi.mocked(api.saveSettings).mockResolvedValue();
  vi.mocked(api.scanOrders).mockResolvedValue(emptyScanResult);
  vi.mocked(api.checkUpdates).mockResolvedValue(null);
  vi.mocked(api.downloadUpdate).mockResolvedValue("");
  vi.mocked(api.installUpdate).mockResolvedValue();
  window.orderQuickRead = api;
});

afterEach(() => {
  vi.useRealTimers();
});

describe("Electron renderer", () => {
  it("collapses settings after saved credentials load", async () => {
    vi.mocked(api.loadSettings).mockResolvedValue({ email: "saved@example.com", authCode: "secret" });

    render(<App />);

    expect(await screen.findByText("saved@example.com")).toBeInTheDocument();
    expect(screen.queryByLabelText("邮箱")).not.toBeInTheDocument();
  });

  it("runs scan all and refresh with the correct scan modes", async () => {
    vi.mocked(api.loadSettings).mockResolvedValue({ email: "saved@example.com", authCode: "secret" });

    render(<App />);

    await screen.findByText("saved@example.com");

    fireEvent.click(screen.getByRole("button", { name: "扫描全部邮件" }));
    await waitFor(() => expect(api.scanOrders).toHaveBeenCalledWith({ fullScan: true }));

    fireEvent.click(screen.getByRole("button", { name: "刷新" }));
    await waitFor(() => expect(api.scanOrders).toHaveBeenLastCalledWith({ fullScan: false }));
  });

  it("filters rendered rows by order number and email sent date range", async () => {
    vi.mocked(api.loadSettings).mockResolvedValue({ email: "saved@example.com", authCode: "secret" });
    vi.mocked(api.scanOrders).mockResolvedValue({
      rows: [
        {
          orderNumber: "SENT-THIS-WEEK",
          deadline: "2026-07-10",
          sourceFile: "",
          messageSubject: "",
          messageDate: "2026-06-16T09:00:00.000Z",
        },
        {
          orderNumber: "SENT-NEXT-WEEK",
          deadline: "2026-06-16",
          sourceFile: "",
          messageSubject: "",
          messageDate: "2026-06-22T09:00:00.000Z",
        },
      ],
      warnings: [],
      scannedMessages: 2,
      parsedAttachments: 2,
      scanMode: "full",
    });

    render(<App />);
    await screen.findByText("saved@example.com");

    fireEvent.click(screen.getByRole("button", { name: "扫描全部邮件" }));
    await screen.findByText("SENT-THIS-WEEK");

    fireEvent.change(screen.getByLabelText("开始日期"), { target: { value: "2026-06-15" } });
    fireEvent.change(screen.getByLabelText("结束日期"), { target: { value: "2026-06-21" } });
    fireEvent.change(screen.getByLabelText("订单号"), { target: { value: "this" } });

    expect(screen.getByText("SENT-THIS-WEEK")).toBeInTheDocument();
    expect(screen.queryByText("SENT-NEXT-WEEK")).not.toBeInTheDocument();
  });

  it("opens settings for editing and collapses them after save", async () => {
    vi.mocked(api.loadSettings).mockResolvedValue({ email: "saved@example.com", authCode: "secret" });

    render(<App />);

    fireEvent.click(await screen.findByRole("button", { name: "修改邮箱设置" }));
    fireEvent.change(screen.getByLabelText("邮箱"), { target: { value: "edited@example.com" } });
    fireEvent.click(screen.getByRole("button", { name: "保存设置" }));

    await waitFor(() =>
      expect(api.saveSettings).toHaveBeenCalledWith({ email: "edited@example.com", authCode: "secret" }),
    );
    expect(await screen.findByText("edited@example.com")).toBeInTheDocument();
    expect(screen.queryByLabelText("邮箱")).not.toBeInTheDocument();
  });

  it("shows API errors as status text without crashing", async () => {
    vi.mocked(api.loadSettings).mockResolvedValue({ email: "saved@example.com", authCode: "secret" });
    vi.mocked(api.scanOrders).mockRejectedValue(new Error("IMAP 登录失败"));

    render(<App />);

    fireEvent.click(await screen.findByRole("button", { name: "刷新" }));

    expect(await screen.findByText("IMAP 登录失败")).toBeInTheDocument();
    expect(screen.getByText("saved@example.com")).toBeInTheDocument();
  });

  it("auto refreshes saved mailbox every 30 seconds", async () => {
    vi.useFakeTimers();
    vi.mocked(api.loadSettings).mockResolvedValue({ email: "saved@example.com", authCode: "secret" });

    render(<App />);

    await act(async () => {
      await Promise.resolve();
      await Promise.resolve();
    });

    expect(screen.getByText("saved@example.com")).toBeInTheDocument();
    expect(api.scanOrders).not.toHaveBeenCalled();

    await act(async () => {
      vi.advanceTimersByTime(30_000);
      await Promise.resolve();
    });

    expect(api.scanOrders).toHaveBeenCalledWith({ fullScan: false });
    expect(screen.getByText("扫描到 0 封邮件，找到 0 个 Excel 附件，读取 0 条订单。")).toBeInTheDocument();
  });

  it("checks for updates on startup without blocking saved settings", async () => {
    vi.mocked(api.loadSettings).mockResolvedValue({ email: "saved@example.com", authCode: "secret" });
    vi.mocked(api.checkUpdates).mockResolvedValue({
      tagName: "v1.2.0",
      releaseUrl: "https://github.com/1192081163/order-quick-read/releases/tag/v1.2.0",
      assetName: "OrderQuickReadSetup.exe",
      assetUrl: "https://example.com/OrderQuickReadSetup.exe",
    });

    render(<App />);

    expect(await screen.findByText("saved@example.com")).toBeInTheDocument();
    expect(await screen.findByText("发现新版本 v1.2.0。")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "下载新版" })).toBeInTheDocument();
  });

  it("downloads and opens an available update from the status action", async () => {
    vi.mocked(api.loadSettings).mockResolvedValue({ email: "saved@example.com", authCode: "secret" });
    vi.mocked(api.checkUpdates).mockResolvedValue({
      tagName: "v1.2.0",
      releaseUrl: "https://github.com/1192081163/order-quick-read/releases/tag/v1.2.0",
      assetName: "OrderQuickReadSetup.exe",
      assetUrl: "https://example.com/OrderQuickReadSetup.exe",
    });
    vi.mocked(api.downloadUpdate).mockResolvedValue("C:\\Users\\admin\\Downloads\\OrderQuickReadSetup.exe");

    render(<App />);

    fireEvent.click(await screen.findByRole("button", { name: "检查更新" }));
    expect(await screen.findByText("发现新版本 v1.2.0。")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "下载新版" }));
    await waitFor(() =>
      expect(api.downloadUpdate).toHaveBeenCalledWith({
        tagName: "v1.2.0",
        releaseUrl: "https://github.com/1192081163/order-quick-read/releases/tag/v1.2.0",
        assetName: "OrderQuickReadSetup.exe",
        assetUrl: "https://example.com/OrderQuickReadSetup.exe",
      }),
    );

    fireEvent.click(await screen.findByRole("button", { name: "打开安装包" }));
    await waitFor(() => expect(api.installUpdate).toHaveBeenCalledWith("C:\\Users\\admin\\Downloads\\OrderQuickReadSetup.exe"));
  });
});
