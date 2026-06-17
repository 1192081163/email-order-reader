import { mkdtemp, readFile, rm, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { scanOrders } from "../../electron/main/services/orderScanner";
import type { EmailAttachment } from "../../electron/main/services/mailClient";
import type { OrderRow } from "../../electron/shared/types";

type MockImapMessage = {
  uid: number;
  source?: Buffer;
  headers?: Buffer;
  bodyStructure?: {
    part?: string;
    type: string;
    parameters?: Record<string, string>;
    disposition?: string;
    dispositionParameters?: Record<string, string>;
    childNodes?: MockImapMessage["bodyStructure"][];
  };
  envelope?: {
    subject?: string;
    date?: Date;
  };
  internalDate?: Date | string;
};

const mailMocks = vi.hoisted(() => {
  type MockClient = {
    connect: ReturnType<typeof vi.fn>;
    getMailboxLock: ReturnType<typeof vi.fn>;
    fetch: ReturnType<typeof vi.fn>;
    downloadMany: ReturnType<typeof vi.fn>;
    logout: ReturnType<typeof vi.fn>;
    mailbox: { uidValidity: bigint; uidNext?: number };
  };

  const state = {
    clients: [] as Array<{ options: unknown; client: MockClient; release: ReturnType<typeof vi.fn> }>,
    messages: [] as MockImapMessage[],
    uidValidity: 123n,
    uidNext: 10,
    connectError: null as Error | null,
    simpleParser: vi.fn(),
    downloads: new Map<string, Buffer>(),
    beforeDownloadMany: null as null | ((range: string, parts: string[]) => Promise<void>),
    ImapFlow: vi.fn((options: unknown) => {
      const release = vi.fn();
      const client: MockClient = {
        connect: vi.fn(async () => {
          if (state.connectError) {
            throw state.connectError;
          }
        }),
        getMailboxLock: vi.fn(async () => ({ release })),
        fetch: vi.fn(() => makeMessageIterator(state.messages)),
        downloadMany: vi.fn(async (range: string, parts: string[]) => {
          await state.beforeDownloadMany?.(range, parts);
          return Object.fromEntries(
            parts.map((part) => [part, { meta: {}, content: state.downloads.get(`${range}:${part}`) ?? null }]),
          );
        }),
        logout: vi.fn(async () => undefined),
        mailbox: { uidValidity: state.uidValidity, uidNext: state.uidNext },
      };
      state.clients.push({ options, client, release });
      return client;
    }),
  };

  async function* makeMessageIterator(messages: MockImapMessage[]): AsyncIterableIterator<MockImapMessage> {
    for (const message of messages) {
      yield message;
    }
  }

  return state;
});

vi.mock("imapflow", () => ({
  ImapFlow: mailMocks.ImapFlow,
}));

vi.mock("mailparser", () => ({
  simpleParser: mailMocks.simpleParser,
}));

let tempDir: string;

beforeEach(async () => {
  tempDir = await mkdtemp(path.join(os.tmpdir(), "order-scanner-"));
  mailMocks.clients = [];
  mailMocks.messages = [];
  mailMocks.uidValidity = 123n;
  mailMocks.uidNext = 10;
  mailMocks.connectError = null;
  mailMocks.downloads = new Map();
  mailMocks.beforeDownloadMany = null;
  mailMocks.simpleParser.mockReset();
  mailMocks.ImapFlow.mockClear();
});

afterEach(async () => {
  await rm(tempDir, { recursive: true, force: true });
});

function attachment(filename: string, uid: number, subject = "orders"): EmailAttachment {
  return {
    filename,
    content: Buffer.from(filename),
    messageSubject: subject,
    messageDate: "2026-06-16T09:00:00.000Z",
    messageUid: uid,
  };
}

function row(orderNumber: string, deadline: string, sourceFile = "orders.xlsx"): OrderRow {
  return {
    orderNumber,
    deadline,
    sourceFile,
    messageSubject: "orders",
    messageDate: "2026-06-16T09:00:00.000Z",
  };
}

describe("Electron order scanner", () => {
  it("parses full scans and saves cache when cache path and account email are provided", async () => {
    const cachePath = path.join(tempDir, "order-cache.json");
    const client = {
      fetchExcelAttachmentBatch: vi.fn(async () => ({
        attachments: [attachment("orders.xlsx", 7)],
        scannedMessages: 1,
        latestUid: 7,
        uidvalidity: "abc",
      })),
    };
    const parseAttachment = vi.fn(() => ({
      filename: "orders.xlsx",
      rows: [row("PO-1", "2026-06-20")],
      warnings: ["parse warning"],
    }));

    const result = await scanOrders({
      client,
      parseAttachment,
      fullScan: true,
      cachePath,
      accountEmail: " buyer@example.com ",
    });

    expect(client.fetchExcelAttachmentBatch).toHaveBeenCalledWith({ sinceUid: undefined });
    expect(parseAttachment).toHaveBeenCalledWith(
      "orders.xlsx",
      Buffer.from("orders.xlsx"),
      "orders",
      "2026-06-16T09:00:00.000Z",
    );
    expect(result).toEqual({
      rows: [row("PO-1", "2026-06-20")],
      warnings: ["parse warning"],
      scannedMessages: 1,
      parsedAttachments: 1,
      scanMode: "full",
    });
    await expect(readFile(cachePath, "utf-8").then(JSON.parse)).resolves.toMatchObject({
      email: "buyer@example.com",
      uidvalidity: "abc",
      lastUid: 7,
      rows: [row("PO-1", "2026-06-20")],
      warnings: ["parse warning"],
      scannedMessages: 1,
      parsedAttachments: 1,
    });
  });

  it("uses cache lastUid for incremental scans and accumulates merged cache metadata", async () => {
    const cachePath = path.join(tempDir, "order-cache.json");
    await writeFile(
      cachePath,
      JSON.stringify({
        email: "buyer@example.com",
        uidvalidity: "abc",
        lastUid: 7,
        rows: [row("PO-1", "2026-06-20", "old.xlsx"), row("PO-2", "2026-06-21", "old.xlsx")],
        warnings: ["old warning"],
        scannedMessages: 3,
        parsedAttachments: 2,
      }),
      "utf-8",
    );
    const updated = row("PO-1", "2026-06-25", "new.xlsx");
    const added = row("PO-3", "2026-06-22", "new.xlsx");
    const client = {
      fetchExcelAttachmentBatch: vi.fn(async () => ({
        attachments: [attachment("new.xlsx", 9)],
        scannedMessages: 2,
        latestUid: 9,
        uidvalidity: "abc",
      })),
    };
    const parseAttachment = vi.fn(() => ({
      filename: "new.xlsx",
      rows: [updated, added],
      warnings: ["new warning"],
    }));

    const result = await scanOrders({
      client,
      parseAttachment,
      fullScan: false,
      cachePath,
      accountEmail: "buyer@example.com",
    });

    expect(client.fetchExcelAttachmentBatch).toHaveBeenCalledTimes(1);
    expect(client.fetchExcelAttachmentBatch).toHaveBeenCalledWith({ sinceUid: 7 });
    expect(result).toEqual({
      rows: [updated, row("PO-2", "2026-06-21", "old.xlsx"), added],
      warnings: ["old warning", "new warning"],
      scannedMessages: 5,
      parsedAttachments: 3,
      scanMode: "incremental",
    });
    await expect(readFile(cachePath, "utf-8").then(JSON.parse)).resolves.toMatchObject({
      email: "buyer@example.com",
      uidvalidity: "abc",
      lastUid: 9,
      rows: [updated, row("PO-2", "2026-06-21", "old.xlsx"), added],
      warnings: ["old warning", "new warning"],
      scannedMessages: 5,
      parsedAttachments: 3,
    });
  });

  it("falls back to full scan when incremental cache account does not match", async () => {
    const cachePath = path.join(tempDir, "order-cache.json");
    await writeFile(
      cachePath,
      JSON.stringify({
        email: "old@example.com",
        uidvalidity: "abc",
        lastUid: 7,
        rows: [row("PO-OLD", "2026-06-20")],
        warnings: ["old warning"],
        scannedMessages: 3,
        parsedAttachments: 1,
      }),
      "utf-8",
    );
    const client = {
      fetchExcelAttachmentBatch: vi.fn(async () => ({
        attachments: [attachment("full.xlsx", 12)],
        scannedMessages: 4,
        latestUid: 12,
        uidvalidity: "new-validity",
      })),
    };
    const parseAttachment = vi.fn(() => ({
      filename: "full.xlsx",
      rows: [row("PO-FULL", "2026-06-26", "full.xlsx")],
      warnings: [],
    }));

    const result = await scanOrders({
      client,
      parseAttachment,
      fullScan: false,
      cachePath,
      accountEmail: "buyer@example.com",
    });

    expect(client.fetchExcelAttachmentBatch).toHaveBeenCalledWith({ sinceUid: undefined });
    expect(result.scanMode).toBe("full");
    expect(result.rows.map((item) => item.orderNumber)).toEqual(["PO-FULL"]);
    await expect(readFile(cachePath, "utf-8").then(JSON.parse)).resolves.toMatchObject({
      email: "buyer@example.com",
      uidvalidity: "new-validity",
      lastUid: 12,
      rows: [row("PO-FULL", "2026-06-26", "full.xlsx")],
      scannedMessages: 4,
      parsedAttachments: 1,
    });
  });

  it("falls back to full scan when uidvalidity changes after incremental fetch", async () => {
    const cachePath = path.join(tempDir, "order-cache.json");
    await writeFile(
      cachePath,
      JSON.stringify({
        email: "buyer@example.com",
        uidvalidity: "old-validity",
        lastUid: 7,
        rows: [row("PO-OLD", "2026-06-20")],
        warnings: [],
        scannedMessages: 3,
        parsedAttachments: 1,
      }),
      "utf-8",
    );
    const client = {
      fetchExcelAttachmentBatch: vi
        .fn()
        .mockResolvedValueOnce({
          attachments: [],
          scannedMessages: 0,
          latestUid: 7,
          uidvalidity: "new-validity",
        })
        .mockResolvedValueOnce({
          attachments: [attachment("full.xlsx", 14)],
          scannedMessages: 5,
          latestUid: 14,
          uidvalidity: "new-validity",
        }),
    };
    const parseAttachment = vi.fn(() => ({
      filename: "full.xlsx",
      rows: [row("PO-FULL", "2026-06-27", "full.xlsx")],
      warnings: [],
    }));

    const result = await scanOrders({
      client,
      parseAttachment,
      fullScan: false,
      cachePath,
      accountEmail: "buyer@example.com",
    });

    expect(client.fetchExcelAttachmentBatch).toHaveBeenNthCalledWith(1, { sinceUid: 7 });
    expect(client.fetchExcelAttachmentBatch).toHaveBeenNthCalledWith(2, { sinceUid: undefined });
    expect(result.scanMode).toBe("full");
    expect(result.rows.map((item) => item.orderNumber)).toEqual(["PO-FULL"]);
  });

  it("falls back to full scan when legacy cache rows are missing message dates", async () => {
    const cachePath = path.join(tempDir, "order-cache.json");
    await writeFile(
      cachePath,
      JSON.stringify({
        email: "buyer@example.com",
        uidvalidity: "abc",
        lastUid: 7,
        rows: [
          {
            orderNumber: "PO-OLD",
            deadline: "2026-06-20",
            sourceFile: "legacy.xlsx",
            messageSubject: "legacy",
          },
        ],
        warnings: [],
        scannedMessages: 3,
        parsedAttachments: 1,
      }),
      "utf-8",
    );
    const client = {
      fetchExcelAttachmentBatch: vi.fn(async () => ({
        attachments: [attachment("full.xlsx", 11)],
        scannedMessages: 2,
        latestUid: 11,
        uidvalidity: "abc",
      })),
    };
    const parseAttachment = vi.fn(() => ({
      filename: "full.xlsx",
      rows: [row("PO-FULL", "2026-06-28", "full.xlsx")],
      warnings: [],
    }));

    const result = await scanOrders({
      client,
      parseAttachment,
      fullScan: false,
      cachePath,
      accountEmail: "buyer@example.com",
    });

    expect(client.fetchExcelAttachmentBatch).toHaveBeenCalledWith({ sinceUid: undefined });
    expect(result.scanMode).toBe("full");
  });
});

describe("IMAP attachment client", () => {
  it("downloads only Excel body parts and preserves message metadata without real network", async () => {
    mailMocks.messages = [
      {
        uid: 7,
        headers: Buffer.from("Date: Tue, 16 Jun 2026 00:30:00 +0800\r\n"),
        bodyStructure: {
          type: "multipart/mixed",
          childNodes: [
            { part: "1", type: "text/plain" },
            {
              part: "2",
              type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
              disposition: "attachment",
              dispositionParameters: { filename: "orders.xlsx" },
            },
            {
              part: "3",
              type: "application/pdf",
              disposition: "attachment",
              dispositionParameters: { filename: "notes.pdf" },
            },
          ],
        },
        envelope: {
          subject: "fallback subject",
          date: new Date("2026-06-16T08:00:00.000Z"),
        },
      },
      {
        uid: 9,
        bodyStructure: {
          type: "multipart/mixed",
          childNodes: [
            {
              part: "1",
              type: "application/octet-stream",
              disposition: "attachment",
              dispositionParameters: { filename: "macro.xlsm" },
            },
            {
              part: "2",
              type: "application/octet-stream",
              disposition: "attachment",
              dispositionParameters: { filename: "legacy.xls" },
            },
          ],
        },
        envelope: {
          subject: "macro orders",
          date: new Date("2026-06-16T10:00:00.000Z"),
        },
      },
    ];
    mailMocks.downloads.set("7:2", Buffer.from("xlsx"));
    mailMocks.downloads.set("9:1", Buffer.from("xlsm"));
    mailMocks.downloads.set("9:2", Buffer.from("xls"));

    const { ImapAttachmentClient } = await import("../../electron/main/services/mailClient");
    const client = new ImapAttachmentClient({
      email: "buyer@example.com",
      authCode: "secret",
      host: "imap.example.com",
      port: 1993,
    });

    const result = await client.fetchExcelAttachmentBatch({ sinceUid: 6 });

    expect(mailMocks.ImapFlow).toHaveBeenCalledWith(
      expect.objectContaining({
        host: "imap.example.com",
        port: 1993,
        secure: true,
        auth: { user: "buyer@example.com", pass: "secret" },
      }),
    );
    expect(mailMocks.clients[0].client.fetch).toHaveBeenCalledWith(
      "7:*",
      { uid: true, envelope: true, internalDate: true, bodyStructure: true, headers: ["date"] },
      { uid: true },
    );
    expect(mailMocks.clients[0].client.downloadMany).toHaveBeenCalledWith("7", ["2"], { uid: true });
    expect(mailMocks.clients[0].client.downloadMany).toHaveBeenCalledWith("9", ["1", "2"], { uid: true });
    expect(mailMocks.simpleParser).not.toHaveBeenCalled();
    expect(mailMocks.clients[0].release).toHaveBeenCalledTimes(1);
    expect(mailMocks.clients[0].client.logout).not.toHaveBeenCalled();
    await client.close();
    expect(mailMocks.clients[0].client.logout).toHaveBeenCalledTimes(1);
    expect(result).toEqual({
      attachments: [
        {
          filename: "orders.xlsx",
          content: Buffer.from("xlsx"),
          messageSubject: "fallback subject",
          messageDate: "2026-06-16T00:30:00+08:00",
          messageUid: 7,
        },
        {
          filename: "macro.xlsm",
          content: Buffer.from("xlsm"),
          messageSubject: "macro orders",
          messageDate: "2026-06-16T10:00:00.000Z",
          messageUid: 9,
        },
        {
          filename: "legacy.xls",
          content: Buffer.from("xls"),
          messageSubject: "macro orders",
          messageDate: "2026-06-16T10:00:00.000Z",
          messageUid: 9,
        },
      ],
      scannedMessages: 2,
      latestUid: 9,
      uidvalidity: "123",
    });
  });

  it("does not refetch the last message when sinceUid reaches mailbox uidNext", async () => {
    mailMocks.uidNext = 10;
    mailMocks.messages = [
      {
        uid: 9,
        source: Buffer.from("message-9"),
      },
    ];
    mailMocks.simpleParser.mockResolvedValue({
      subject: "should not parse",
      headerLines: [],
      attachments: [{ filename: "orders.xlsx", content: Buffer.from("xlsx") }],
    });

    const { ImapAttachmentClient } = await import("../../electron/main/services/mailClient");
    const client = new ImapAttachmentClient({
      email: "buyer@example.com",
      authCode: "secret",
      host: "imap.example.com",
    });

    const result = await client.fetchExcelAttachmentBatch({ sinceUid: 9 });

    expect(mailMocks.clients[0].client.fetch).not.toHaveBeenCalled();
    expect(mailMocks.clients[0].release).toHaveBeenCalledTimes(1);
    expect(result).toEqual({
      attachments: [],
      scannedMessages: 0,
      latestUid: 9,
      uidvalidity: "123",
    });
  });

  it("reuses the IMAP connection across repeated refreshes", async () => {
    mailMocks.uidNext = 10;

    const { ImapAttachmentClient } = await import("../../electron/main/services/mailClient");
    const client = new ImapAttachmentClient({
      email: "buyer@example.com",
      authCode: "secret",
      host: "imap.example.com",
    });

    await client.fetchExcelAttachmentBatch({ sinceUid: 9 });
    await client.fetchExcelAttachmentBatch({ sinceUid: 9 });

    expect(mailMocks.ImapFlow).toHaveBeenCalledTimes(1);
    expect(mailMocks.clients[0].client.connect).toHaveBeenCalledTimes(1);
    expect(mailMocks.clients[0].client.logout).not.toHaveBeenCalled();

    await client.close();

    expect(mailMocks.clients[0].client.logout).toHaveBeenCalledTimes(1);
  });

  it("starts attachment downloads from multiple messages concurrently", async () => {
    mailMocks.uidNext = 12;
    mailMocks.messages = [
      {
        uid: 7,
        bodyStructure: {
          type: "multipart/mixed",
          childNodes: [
            {
              part: "2",
              type: "application/octet-stream",
              disposition: "attachment",
              dispositionParameters: { filename: "first.xlsx" },
            },
          ],
        },
        envelope: { subject: "first", date: new Date("2026-06-16T08:00:00.000Z") },
      },
      {
        uid: 8,
        bodyStructure: {
          type: "multipart/mixed",
          childNodes: [
            {
              part: "2",
              type: "application/octet-stream",
              disposition: "attachment",
              dispositionParameters: { filename: "second.xlsx" },
            },
          ],
        },
        envelope: { subject: "second", date: new Date("2026-06-16T09:00:00.000Z") },
      },
    ];
    mailMocks.downloads.set("7:2", Buffer.from("first"));
    mailMocks.downloads.set("8:2", Buffer.from("second"));
    const startedDownloads: string[] = [];
    let releaseFirstDownload: () => void = () => undefined;
    mailMocks.beforeDownloadMany = async (range) => {
      startedDownloads.push(range);
      if (range === "7") {
        await new Promise<void>((resolve) => {
          releaseFirstDownload = resolve;
        });
      }
    };

    const { ImapAttachmentClient } = await import("../../electron/main/services/mailClient");
    const client = new ImapAttachmentClient({
      email: "buyer@example.com",
      authCode: "secret",
      host: "imap.example.com",
    });

    const scanPromise = client.fetchExcelAttachmentBatch({ sinceUid: 6 });
    await new Promise((resolve) => setTimeout(resolve, 0));
    const downloadsStartedBeforeFirstFinished = [...startedDownloads];
    releaseFirstDownload();
    const result = await scanPromise;

    expect(downloadsStartedBeforeFirstFinished).toEqual(["7", "8"]);
    expect(result.attachments.map((item) => item.filename)).toEqual(["first.xlsx", "second.xlsx"]);
  });

  it("formats Enterprise WeChat login failures in Chinese", async () => {
    mailMocks.connectError = new Error(
      "Login fail. Account is abnormal, service is not open, password is incorrect, login frequency limited, or system is busy.",
    );

    const { ImapAttachmentClient } = await import("../../electron/main/services/mailClient");
    const client = new ImapAttachmentClient({
      email: "buyer@example.com",
      authCode: "secret",
      host: "imap.example.com",
    });

    let errorMessage = "";
    try {
      await client.fetchExcelAttachmentBatch({});
    } catch (error) {
      errorMessage = error instanceof Error ? error.message : String(error);
    }

    expect(errorMessage).toContain("邮箱登录失败");
    expect(errorMessage).toContain("授权码");
    expect(errorMessage).toContain("IMAP/SMTP");
    expect(errorMessage).toContain("登录频率");
  });
});
