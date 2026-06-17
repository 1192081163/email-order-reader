import { ImapFlow, type ImapFlowOptions, type MessageStructureObject } from "imapflow";

const SUPPORTED_EXCEL_EXTENSION = /\.(xlsx|xlsm|xls)$/i;
const MAX_ATTACHMENT_DOWNLOADS = 3;

export const ENTERPRISE_WECHAT_IMAP_HOST = "imap.exmail.qq.com";

export type ImapConfig = {
  email: string;
  authCode: string;
  host?: string;
  port?: number;
  secure?: boolean;
};

export type EmailAttachment = {
  filename: string;
  content: Buffer;
  messageSubject: string;
  messageDate: string;
  messageUid: number;
};

export type AttachmentBatch = {
  attachments: EmailAttachment[];
  scannedMessages: number;
  latestUid: number;
  uidvalidity: string;
};

export type AttachmentFetchOptions = {
  sinceUid?: number;
};

export type AttachmentClient = {
  fetchExcelAttachmentBatch(options: AttachmentFetchOptions): Promise<AttachmentBatch>;
  close?(): Promise<void>;
};

type SelectedMailbox = {
  uidValidity?: bigint | number | string;
  uidNext?: number;
};

type ExcelBodyPart = {
  part: string;
  filename: string;
};

type AttachmentDownloadJob = {
  uid: number;
  excelParts: ExcelBodyPart[];
  messageSubject: string;
  messageDate: string;
};

export class ImapAttachmentClient implements AttachmentClient {
  private client: ImapFlow | null = null;
  private connecting: Promise<ImapFlow> | null = null;

  constructor(private readonly config: ImapConfig) {}

  async fetchExcelAttachmentBatch(options: AttachmentFetchOptions): Promise<AttachmentBatch> {
    const client = await this.connectedClient();
    const attachments: EmailAttachment[] = [];
    const downloadJobs: AttachmentDownloadJob[] = [];
    let scannedMessages = 0;
    let latestUid = options.sinceUid ?? 0;
    let uidvalidity = "";

    try {
      const lock = await client.getMailboxLock("INBOX");
      try {
        const mailbox = client.mailbox as SelectedMailbox | false;
        uidvalidity = mailbox ? String(mailbox.uidValidity ?? "") : "";
        if (isNoNewUidRange(options.sinceUid, mailbox ? mailbox.uidNext : undefined)) {
          return { attachments, scannedMessages, latestUid, uidvalidity };
        }

        const fetchRange = createFetchRange(options.sinceUid);
        for await (const message of client.fetch(
          fetchRange,
          { uid: true, envelope: true, internalDate: true, bodyStructure: true, headers: ["date"] },
          { uid: true },
        )) {
          if (options.sinceUid !== undefined && message.uid <= options.sinceUid) {
            continue;
          }

          scannedMessages += 1;
          latestUid = Math.max(latestUid, message.uid);
          const excelParts = collectExcelBodyParts(message.bodyStructure);
          if (excelParts.length === 0) {
            continue;
          }

          const messageSubject = message.envelope?.subject ?? "";
          const messageDate = messageDateFromHeaders(message.headers, message.envelope?.date ?? message.internalDate);
          downloadJobs.push({
            uid: message.uid,
            excelParts,
            messageSubject,
            messageDate,
          });
        }

        const downloadedAttachments = await mapWithConcurrency(
          downloadJobs,
          MAX_ATTACHMENT_DOWNLOADS,
          async (job) => downloadExcelAttachments(client, job),
        );
        for (const attachmentGroup of downloadedAttachments) {
          attachments.push(...attachmentGroup);
        }
      } finally {
        lock.release();
      }
    } catch (error) {
      await this.close();
      throw error;
    }

    return { attachments, scannedMessages, latestUid, uidvalidity };
  }

  async close(): Promise<void> {
    const client = this.client;
    this.client = null;
    this.connecting = null;
    await client?.logout().catch(() => undefined);
  }

  private async connectedClient(): Promise<ImapFlow> {
    if (this.client) {
      return this.client;
    }
    if (this.connecting) {
      return this.connecting;
    }

    const client = new ImapFlow(this.createClientOptions());
    this.connecting = client
      .connect()
      .then(() => {
        this.client = client;
        return client;
      })
      .catch((error: unknown) => {
        this.client = null;
        throw new Error(formatLoginError(error));
      })
      .finally(() => {
        this.connecting = null;
      });

    return this.connecting;
  }

  private createClientOptions(): ImapFlowOptions {
    return {
      host: this.config.host ?? ENTERPRISE_WECHAT_IMAP_HOST,
      port: this.config.port ?? 993,
      secure: this.config.secure ?? true,
      auth: {
        user: this.config.email,
        pass: this.config.authCode,
      },
    };
  }
}

function createFetchRange(sinceUid: number | undefined): string {
  if (sinceUid === undefined || sinceUid <= 0) {
    return "1:*";
  }
  return `${sinceUid + 1}:*`;
}

function isNoNewUidRange(sinceUid: number | undefined, uidNext: number | undefined): boolean {
  return sinceUid !== undefined && sinceUid > 0 && uidNext !== undefined && sinceUid + 1 >= uidNext;
}

function isExcelFilename(filename: string): boolean {
  return SUPPORTED_EXCEL_EXTENSION.test(filename);
}

function collectExcelBodyParts(structure: MessageStructureObject | undefined): ExcelBodyPart[] {
  if (!structure) {
    return [];
  }

  const parts: ExcelBodyPart[] = [];
  collectExcelBodyPartsInto(structure, parts);
  return parts;
}

async function downloadExcelAttachments(client: ImapFlow, job: AttachmentDownloadJob): Promise<EmailAttachment[]> {
  const downloads = await client.downloadMany(
    String(job.uid),
    job.excelParts.map((part) => part.part),
    { uid: true },
  );
  const attachments: EmailAttachment[] = [];

  for (const excelPart of job.excelParts) {
    const content = downloads[excelPart.part]?.content;
    if (!content) {
      continue;
    }

    attachments.push({
      filename: excelPart.filename,
      content,
      messageSubject: job.messageSubject,
      messageDate: job.messageDate,
      messageUid: job.uid,
    });
  }

  return attachments;
}

async function mapWithConcurrency<TInput, TResult>(
  items: TInput[],
  concurrency: number,
  mapper: (item: TInput) => Promise<TResult>,
): Promise<TResult[]> {
  if (items.length === 0) {
    return [];
  }

  const results = new Array<TResult>(items.length);
  let nextIndex = 0;
  const workerCount = Math.min(Math.max(1, concurrency), items.length);

  await Promise.all(
    Array.from({ length: workerCount }, async () => {
      while (nextIndex < items.length) {
        const index = nextIndex;
        nextIndex += 1;
        results[index] = await mapper(items[index]);
      }
    }),
  );

  return results;
}

function collectExcelBodyPartsInto(node: MessageStructureObject, parts: ExcelBodyPart[]): void {
  const filename = filenameFromStructure(node);
  if (node.part && isExcelFilename(filename)) {
    parts.push({ part: node.part, filename });
  }

  for (const child of node.childNodes ?? []) {
    collectExcelBodyPartsInto(child, parts);
  }
}

function filenameFromStructure(node: MessageStructureObject): string {
  return node.dispositionParameters?.filename ?? node.parameters?.name ?? "";
}

function messageDateFromHeaders(headers: Buffer | undefined, fallback: Date | string | undefined): string {
  const rawDateHeader = headers
    ?.toString("utf-8")
    .split(/\r?\n/)
    .find((line) => /^date:/i.test(line));
  const dateFromHeader = rawDateHeader ? rfcDateHeaderToIso(rawDateHeader) : "";
  if (dateFromHeader) {
    return dateFromHeader;
  }

  return toIsoDate(fallback);
}

function rfcDateHeaderToIso(rawHeader: string): string {
  const value = rawHeader.replace(/^date:\s*/i, "").trim();
  const match = value.match(
    /^(?:[A-Za-z]{3},\s*)?(\d{1,2})\s+([A-Za-z]{3})\s+(\d{4})\s+(\d{1,2}):(\d{2})(?::(\d{2}))?\s+([+-]\d{2}:?\d{2})\b/i,
  );
  if (!match) {
    return "";
  }

  const [, dayText, monthText, yearText, hourText, minuteText, secondText = "00", offsetText] = match;
  const month = monthNumber(monthText);
  const day = Number(dayText);
  const year = Number(yearText);
  const hour = Number(hourText);
  const minute = Number(minuteText);
  const second = Number(secondText);
  const normalizedOffset = normalizeOffset(offsetText);
  if (
    month === 0 ||
    !isValidDateTimeParts(year, month, day, hour, minute, second) ||
    normalizedOffset === ""
  ) {
    return "";
  }

  return `${String(year).padStart(4, "0")}-${String(month).padStart(2, "0")}-${String(day).padStart(2, "0")}T${String(hour).padStart(2, "0")}:${String(minute).padStart(2, "0")}:${String(second).padStart(2, "0")}${normalizedOffset}`;
}

function monthNumber(monthText: string): number {
  return ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"].indexOf(
    monthText.toLowerCase(),
  ) + 1;
}

function normalizeOffset(offsetText: string): string {
  const match = offsetText.match(/^([+-])(\d{2}):?(\d{2})$/);
  if (!match) {
    return "";
  }

  const [, sign, hours, minutes] = match;
  return `${sign}${hours}:${minutes}`;
}

function isValidDateTimeParts(year: number, month: number, day: number, hour: number, minute: number, second: number): boolean {
  const date = new Date(Date.UTC(year, month - 1, day, hour, minute, second));
  return (
    date.getUTCFullYear() === year &&
    date.getUTCMonth() === month - 1 &&
    date.getUTCDate() === day &&
    date.getUTCHours() === hour &&
    date.getUTCMinutes() === minute &&
    date.getUTCSeconds() === second
  );
}

function toIsoDate(value: Date | string | undefined): string {
  if (value instanceof Date) {
    return value.toISOString();
  }
  if (typeof value !== "string" || !value) {
    return "";
  }

  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? "" : parsed.toISOString();
}

function formatLoginError(error: unknown): string {
  const rawMessage = exceptionText(error);
  if (rawMessage.toLowerCase().includes("login fail")) {
    return (
      "邮箱登录失败：企业微信拒绝登录。请检查企业微信邮箱是否已开启 IMAP/SMTP 服务、" +
      "授权码是否正确；如果刚连续刷新多次，可能触发登录频率限制，请等待几分钟后再试。"
    );
  }

  return `邮箱登录失败：${rawMessage}`;
}

function exceptionText(error: unknown): string {
  if (error instanceof Error && error.message) {
    return error.message;
  }
  return String(error);
}
