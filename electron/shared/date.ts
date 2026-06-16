const DATE_PATTERNS = [
  /^\s*(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})(?:\s+\d{1,2}:\d{2}(?::\d{2})?)?\s*$/,
  /^\s*(\d{4})年\s*(\d{1,2})月\s*(\d{1,2})日(?:\s*\d{1,2}:\d{2}(?::\d{2})?)?\s*$/,
];

export function normalizeDeadlineDate(value: string): string | null {
  for (const pattern of DATE_PATTERNS) {
    const match = value.match(pattern);
    if (!match) {
      continue;
    }

    const [, yearText, monthText, dayText] = match;
    const year = Number(yearText);
    const month = Number(monthText);
    const day = Number(dayText);
    const date = new Date(Date.UTC(year, month - 1, day));

    if (
      date.getUTCFullYear() !== year ||
      date.getUTCMonth() !== month - 1 ||
      date.getUTCDate() !== day
    ) {
      return null;
    }

    return `${String(year).padStart(4, "0")}-${String(month).padStart(2, "0")}-${String(day).padStart(2, "0")}`;
  }

  return null;
}

export function sentDateFromMessageDate(value: string): string | null {
  const text = value.trim();
  if (!text) {
    return null;
  }

  const isoDateMatch = text.match(/^(\d{4}-\d{2}-\d{2})/);
  if (isoDateMatch) {
    return isoDateMatch[1];
  }

  const date = new Date(text);
  if (Number.isNaN(date.getTime())) {
    return null;
  }

  return date.toISOString().slice(0, 10);
}
