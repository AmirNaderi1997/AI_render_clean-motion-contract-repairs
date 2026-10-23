/** "About 40 seconds left" / "about 2 minutes left", from the server's measured estimate (counted down between updates). */
export function etaText(deadline: number | null, now: number): string {
  if (deadline === null) return "";
  const left = Math.max(0, Math.round(deadline - now));
  const fa = (n: number) => new Intl.NumberFormat("fa-IR").format(n);
  if (left < 8) return "چند ثانیهٔ دیگر";
  if (left < 75) return `حدود ${fa(Math.round(left / 5) * 5)} ثانیه مانده`;
  return `حدود ${fa(Math.round(left / 60))} دقیقه مانده`;
}
