import { mkdtemp, rm, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { loadOrderCache } from "../../electron/main/services/orderCache";
import {
  loadRemoteEmailApiConfig,
  RemoteEmailApiClient,
  scanRemoteOrders,
} from "../../electron/main/services/remoteEmailApi";

let tempDir: string;

beforeEach(async () => {
  tempDir = await mkdtemp(path.join(os.tmpdir(), "remote-email-api-"));
});

afterEach(async () => {
  vi.unstubAllGlobals();
  await rm(tempDir, { recursive: true, force: true });
});

function extractionValues(orderNumber: string, deadline: string): Array<string | number | null> {
  const values = Array<string | number | null>(24).fill("");
  values[0] = "2026-07-02";
  values[1] = orderNumber;
  values[14] = deadline;
  return values;
}

function extractionRow(values: Array<string | number | null>, sourceFile = "/server/downloads/order.xlsx") {
  return {
    values,
    notes: [],
    manualCheck: [],
    sourceFile,
  };
}

function message(uid: string, subject = `order ${uid}`) {
  return {
    uid,
    subject,
    date: "2026-06-18T02:00:00.000Z",
    attachmentCount: 1,
    excelAttachmentNames: [`${uid}.xlsx`],
    hasExcelAttachments: true,
  };
}

function listPayload(messages: Array<ReturnType<typeof message>>) {
  return {
    messages,
    scannedMessages: messages.length,
    days: 7,
  };
}

function extractionPayload(uid: string, rows = [extractionRow(extractionValues(`PO-${uid}`, "2026-07-05"), `/server/${uid}.xlsx`)]) {
  return {
    emailFetch: {
      files: [`/server/${uid}.xlsx`],
      scannedMessages: 1,
      attachmentCount: rows.length,
      downloadDir: "/server",
    },
    extraction: {
      inputFiles: [`/server/${uid}.xlsx`],
      rows,
      skippedFiles: [],
      failures: [],
      outputs: {
        outputDir: "",
        csvOutput: "",
        xlsxOutput: "",
        auditOutput: "",
      },
    },
  };
}

describe("remote email API client", () => {
  it("loads remote API config from environment before JSON files", async () => {
    const configPath = path.join(tempDir, "email_api_client.json");
    await writeFile(configPath, JSON.stringify({ baseUrl: "https://json.example", token: "json-token" }), "utf-8");

    await expect(
      loadRemoteEmailApiConfig(
        { ORDERFLOW_EMAIL_API_URL: " https://env.example/ ", ORDERFLOW_EMAIL_API_TOKEN: " env-token " },
        [configPath],
      ),
    ).resolves.toEqual({
      baseUrl: "https://env.example/",
      token: "env-token",
    });
  });

  it("scans server messages and maps extracted rows into order rows", async () => {
    const cachePath = path.join(tempDir, "order_cache.json");
    const fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
      if (url === "https://api.example/api/email/messages") {
        return new Response(JSON.stringify(listPayload([message("101", "new order")])), { status: 200 });
      }

      if (url === "https://api.example/api/email/extract") {
        return new Response(JSON.stringify(extractionPayload("101")), { status: 200 });
      }

      return new Response("Not found", { status: 404 });
    });
    vi.stubGlobal("fetch", fetchMock);

    const result = await scanRemoteOrders({
      client: new RemoteEmailApiClient({ baseUrl: "https://api.example/", token: "secret-token" }),
      request: {
        fullScan: true,
        sentStartDate: "2026-06-12",
        sentEndDate: "2026-06-18",
      },
      cachePath,
      accountEmail: "remote@example.com",
      now: () => new Date("2026-06-18T12:00:00.000Z"),
    });

    expect(fetchMock).toHaveBeenNthCalledWith(
      1,
      "https://api.example/api/email/messages",
      expect.objectContaining({
        method: "POST",
        headers: expect.objectContaining({ Authorization: "Bearer secret-token" }),
        body: JSON.stringify({ days: 7 }),
      }),
    );
    expect(fetchMock).toHaveBeenNthCalledWith(
      2,
      "https://api.example/api/email/extract",
      expect.objectContaining({
        method: "POST",
        headers: expect.objectContaining({ Authorization: "Bearer secret-token" }),
        body: JSON.stringify({ messageUids: ["101"], hours: 168, inferManual: true }),
      }),
    );
    expect(result).toMatchObject({
      rows: [
        {
          orderNumber: "PO-101",
          deadline: "2026-07-05",
          sourceFile: "101.xlsx",
          messageSubject: "new order",
          messageDate: "2026-06-18T02:00:00.000Z",
        },
      ],
      scannedMessages: 1,
      parsedAttachments: 1,
      scanMode: "full",
    });
    await expect(loadOrderCache(cachePath)).resolves.toMatchObject({
      email: "remote@example.com",
      lastUid: 101,
      rows: result.rows,
    });
  });

  it("does not expand remote scans to the background backfill window", async () => {
    const cachePath = path.join(tempDir, "order_cache.json");
    const fetchMock = vi.fn(async (url: string) => {
      if (url.endsWith("/api/email/messages")) {
        return new Response(JSON.stringify(listPayload([])), { status: 200 });
      }
      return new Response("Not found", { status: 404 });
    });
    vi.stubGlobal("fetch", fetchMock);

    await scanRemoteOrders({
      client: new RemoteEmailApiClient({ baseUrl: "https://api.example" }),
      request: {
        fullScan: true,
        sentStartDate: "2026-06-12",
        sentEndDate: "2026-06-18",
        backgroundBackfill: true,
        backgroundSentStartDate: "2026-05-20",
        backgroundSentEndDate: "2026-06-18",
      },
      cachePath,
      accountEmail: "remote@example.com",
      now: () => new Date("2026-06-18T12:00:00.000Z"),
    });

    expect(fetchMock).toHaveBeenCalledWith(
      "https://api.example/api/email/messages",
      expect.objectContaining({
        body: JSON.stringify({ days: 7 }),
      }),
    );
  });

  it("extracts messages in small batches and keeps partial results when a batch fails", async () => {
    const cachePath = path.join(tempDir, "order_cache.json");
    const messages = ["101", "102", "103", "104", "105", "106"].map((uid) => message(uid));
    const fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
      if (url.endsWith("/api/email/messages")) {
        return new Response(JSON.stringify(listPayload(messages)), { status: 200 });
      }
      if (url.endsWith("/api/email/extract")) {
        const body = JSON.parse(String(init?.body));
        if (body.messageUids.includes("106")) {
          return new Response(JSON.stringify({ error: "TLS disconnected" }), { status: 500 });
        }
        return new Response(
          JSON.stringify({
            emailFetch: {
              files: body.messageUids.map((uid: string) => `/server/${uid}.xlsx`),
              scannedMessages: body.messageUids.length,
              attachmentCount: body.messageUids.length,
              downloadDir: "/server",
            },
            extraction: {
              inputFiles: body.messageUids.map((uid: string) => `/server/${uid}.xlsx`),
              rows: body.messageUids.map((uid: string) =>
                extractionRow(extractionValues(`PO-${uid}`, "2026-07-05"), `/server/${uid}.xlsx`),
              ),
              skippedFiles: [],
              failures: [],
              outputs: { outputDir: "", csvOutput: "", xlsxOutput: "", auditOutput: "" },
            },
          }),
          { status: 200 },
        );
      }
      return new Response("Not found", { status: 404 });
    });
    vi.stubGlobal("fetch", fetchMock);

    const result = await scanRemoteOrders({
      client: new RemoteEmailApiClient({ baseUrl: "https://api.example" }),
      request: { fullScan: true, sentStartDate: "2026-06-12", sentEndDate: "2026-06-18" },
      cachePath,
      accountEmail: "remote@example.com",
      now: () => new Date("2026-06-18T12:00:00.000Z"),
    });

    const extractCalls = fetchMock.mock.calls.filter(([url]) => String(url).endsWith("/api/email/extract"));
    expect(extractCalls).toHaveLength(2);
    expect(JSON.parse(String(extractCalls[0][1]?.body)).messageUids).toEqual(["101", "102", "103", "104", "105"]);
    expect(JSON.parse(String(extractCalls[1][1]?.body)).messageUids).toEqual(["106"]);
    expect(result.rows.map((row) => row.orderNumber)).toEqual(["PO-101", "PO-102", "PO-103", "PO-104", "PO-105"]);
    expect(result.warnings).toContain("远端邮件服务提取失败 UID 106：TLS disconnected");
  });

  it("reuses cached remote extraction results by UID", async () => {
    const cachePath = path.join(tempDir, "order_cache.json");
    const fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
      if (url.endsWith("/api/email/messages")) {
        return new Response(JSON.stringify(listPayload([message("101")])), { status: 200 });
      }
      if (url.endsWith("/api/email/extract")) {
        const body = JSON.parse(String(init?.body));
        return new Response(JSON.stringify(extractionPayload(body.messageUids[0])), { status: 200 });
      }
      return new Response("Not found", { status: 404 });
    });
    vi.stubGlobal("fetch", fetchMock);
    const client = new RemoteEmailApiClient({ baseUrl: "https://api.example" });
    const request = { fullScan: true, sentStartDate: "2026-06-12", sentEndDate: "2026-06-18" };

    await scanRemoteOrders({
      client,
      request,
      cachePath,
      accountEmail: "remote@example.com",
      now: () => new Date("2026-06-18T12:00:00.000Z"),
    });
    await scanRemoteOrders({
      client,
      request,
      cachePath,
      accountEmail: "remote@example.com",
      now: () => new Date("2026-06-18T12:00:00.000Z"),
    });

    const extractCalls = fetchMock.mock.calls.filter(([url]) => String(url).endsWith("/api/email/extract"));
    expect(extractCalls).toHaveLength(1);
    await expect(loadOrderCache(cachePath)).resolves.toMatchObject({
      parsedAttachmentCache: [
        {
          key: "remote-email-api:101",
          rows: [
            expect.objectContaining({
              orderNumber: "PO-101",
            }),
          ],
        },
      ],
    });
  });
});
