import { Notification } from "electron";

import type { OrderRow } from "../../shared/types.js";

export type OrderChangeSummary = {
  newCount: number;
  updatedCount: number;
};

export function countOrderChanges(previousRows: OrderRow[], nextRows: OrderRow[]): OrderChangeSummary {
  const previousByOrderNumber = new Map(previousRows.map((row) => [row.orderNumber, row.deadline]));
  let newCount = 0;
  let updatedCount = 0;

  for (const row of nextRows) {
    const previousDeadline = previousByOrderNumber.get(row.orderNumber);
    if (previousDeadline === undefined) {
      newCount += 1;
    } else if (previousDeadline !== row.deadline) {
      updatedCount += 1;
    }
  }

  return { newCount, updatedCount };
}

export function notifyOrderChanges(summary: OrderChangeSummary): void {
  const parts: string[] = [];
  if (summary.newCount > 0) {
    parts.push(`新增 ${summary.newCount} 条订单`);
  }
  if (summary.updatedCount > 0) {
    parts.push(`更新 ${summary.updatedCount} 条订单`);
  }
  if (!parts.length || !Notification.isSupported()) {
    return;
  }

  new Notification({
    title: "邮件订单更新",
    body: parts.join("，"),
  }).show();
}
