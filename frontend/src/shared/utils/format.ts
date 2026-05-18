import type { Locale } from '../types/scientific-kb'

export function normalizeNumber(value: unknown): number {
  return typeof value === 'number' && Number.isFinite(value) ? value : 0
}

export function clampPercentValue(value: unknown): number {
  if (typeof value !== 'number' || !Number.isFinite(value)) return 0
  return Math.max(0, Math.min(100, value * 100))
}

export function formatPercent(value: unknown): string {
  if (typeof value !== 'number' || !Number.isFinite(value)) return '-'
  return `${Math.round(value * 100)}%`
}

export function formatPages(count: unknown, locale: Locale): string {
  const value = normalizeNumber(count)

  if (locale === 'ru') {
    const mod10 = value % 10
    const mod100 = value % 100

    if (mod10 === 1 && mod100 !== 11) return `${value} страница`
    if ([2, 3, 4].includes(mod10) && ![12, 13, 14].includes(mod100)) return `${value} страницы`
    return `${value} страниц`
  }

  return value === 1 ? `${value} page` : `${value} pages`
}
