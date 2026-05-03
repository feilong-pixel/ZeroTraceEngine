export function formatDisplayTime(value) {
  const text = String(value ?? "").trim();
  if (!text || text === "-") return "-";

  const isoMatch = text.match(
    /^(\d{4})-(\d{2})-(\d{2})[T\s](\d{2}):(\d{2}):(\d{2})(?:\.(\d+))?/,
  );
  if (isoMatch) {
    const [, year, month, day, hour, minute, second, fraction = ""] = isoMatch;
    return buildDisplayTime(year, month, day, hour, minute, second, fraction);
  }

  const exifMatch = text.match(
    /^(\d{4}):(\d{2}):(\d{2})\s+(\d{2}):(\d{2}):(\d{2})(?:\.(\d+))?/,
  );
  if (exifMatch) {
    const [, year, month, day, hour, minute, second, fraction = ""] = exifMatch;
    return buildDisplayTime(year, month, day, hour, minute, second, fraction);
  }

  return text;
}

function buildDisplayTime(year, month, day, hour, minute, second, fraction) {
  const centiseconds = String(fraction || "").padEnd(2, "0").slice(0, 2);
  return `${year}-${month}-${day} ${hour}:${minute}:${second}.${centiseconds}`;
}
