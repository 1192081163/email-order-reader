export type OrderRow = {
  orderNumber: string;
  deadline: string;
  sourceFile: string;
  messageSubject: string;
  messageDate: string;
};

export type ScanResult = {
  rows: OrderRow[];
  warnings: string[];
  scannedMessages: number;
  parsedAttachments: number;
  scanMode: "full" | "incremental";
};

export type AppSettings = {
  email: string;
  authCode: string;
};

export type DateFilter = {
  searchText: string;
  startDate: string;
  endDate: string;
};

export type UpdateInfo = {
  tagName: string;
  releaseUrl: string;
  assetName: string;
  assetUrl: string;
};
