import { subDays, formatISO } from 'date-fns'

/** Returns a Date 30 days ago (start of default date range). */
export function defaultStartDate(): Date {
  return subDays(new Date(), 30)
}

/** Returns the current Date (end of default date range). */
export function defaultEndDate(): Date {
  return new Date()
}

/** Format a Date as an ISO string (YYYY-MM-DDTHH:mm:ss). */
export function toISOString(date: Date): string {
  return formatISO(date)
}

/** Format a Date for display (locale-sensitive short format). */
export function formatDisplay(date: Date): string {
  return date.toLocaleString()
}
