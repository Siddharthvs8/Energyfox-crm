// Short Indian form (₹2.15 Cr / ₹69.35 L) so big amounts fit narrow phone cards.
export function compactINR(n: number) {
  const trim = (x: number) => x.toFixed(2).replace(/\.?0+$/, "");
  if (n >= 1e7) return `${trim(n / 1e7)} Cr`;
  if (n >= 1e5) return `${trim(n / 1e5)} L`;
  return n.toLocaleString("en-IN");
}
