/**
 * Returns the single EnergyFox backend base URL.
 *
 * Prefers `NEXT_PUBLIC_API_BASE` (e.g. "http://localhost:8000" in dev,
 * "https://crm.energyfox.com" in prod). If unset, falls back to the current
 * origin with an optional API port — useful when nginx proxies /api to the
 * backend on the same host.
 *
 * The optional argument is ignored; it exists only so legacy call sites that
 * still pass a value continue to type-check after the multi-tenant removal.
 */
export function getApiBase(_domain?: string): string {
  const base = process.env.NEXT_PUBLIC_API_BASE;
  if (base) return base.replace(/\/$/, '');

  const protocol = process.env.NEXT_PUBLIC_API_PROTOCOL || 'http';
  const port = process.env.NEXT_PUBLIC_API_PORT;
  const portSuffix = port ? `:${port}` : '';

  if (typeof window !== 'undefined') {
    return `${protocol}://${window.location.hostname}${portSuffix}`;
  }
  return `${protocol}://localhost${portSuffix || ':8000'}`;
}

/**
 * Formats a currency value in INR locale.
 */
export function formatCurrency(value: number): string {
  return value.toLocaleString('en-IN', { minimumFractionDigits: 0 });
}

export function formatNumber(value: number): string {
  return value.toLocaleString('en-IN', { minimumFractionDigits: 0 });
}

/**
 * Maps source slugs to display labels.
 */
export function getSourceLabel(source: string): string {
  const labels: Record<string, string> = {
    manual: 'Manual',
    meta: 'Meta Ads',
    meta_ads: 'Meta Ads',
    website: 'Website',
    referral: 'Referral',
    linkedin: 'LinkedIn',
  };
  return labels[source] || source;
}
