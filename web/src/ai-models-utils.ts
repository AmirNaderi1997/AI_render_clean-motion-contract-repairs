export function movePriority(order: string[], from: number, to: number): string[] {
  if (from < 0 || to < 0 || from >= order.length || to >= order.length) return [...order];
  const next = [...order]; next.splice(to, 0, next.splice(from, 1)[0]); return next;
}

export function logQuery(filters: Record<string, string>): string {
  const params = new URLSearchParams();
  Object.entries(filters).forEach(([key,value]) => {
    if (value) params.set(key, key === "since" ? `${value}T00:00:00+00:00` : key === "until" ? `${value}T23:59:59+00:00` : value);
  });
  return params.toString();
}
