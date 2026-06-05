// Phase 12 — per-job log helpers.
//
// `fetchJobLogs` parses the `application/x-ndjson` stream from
// `GET /api/logs/{jobId}` into an array of `LogLine` records (used by
// JobLogsCard to seed its pane on mount).
//
// `downloadJobLogsZip` triggers a browser download for the per-job zip.
// We can't put the JWT on a plain `<a href>`, so we fetch the bytes as
// a blob, build a temporary object URL, and click an anchor at it.

import { getToken } from './client'
import type { LogLine } from './types'

const API_BASE = (import.meta.env.VITE_API_BASE as string | undefined) ?? ''

export async function fetchJobLogs(jobId: string, limit = 200): Promise<LogLine[]> {
  const token = getToken()
  const headers: Record<string, string> = {}
  if (token) headers['Authorization'] = `Bearer ${token}`
  const url = `${API_BASE}/api/logs/${encodeURIComponent(jobId)}?limit=${limit}`
  const resp = await fetch(url, { headers })
  if (!resp.ok) {
    throw new Error(`fetch logs failed: ${resp.status}`)
  }
  const text = await resp.text()
  const lines: LogLine[] = []
  for (const raw of text.split('\n')) {
    const trimmed = raw.trim()
    if (!trimmed) continue
    try {
      lines.push(JSON.parse(trimmed) as LogLine)
    } catch {
      // Skip non-JSON lines defensively — the backend already filters
      // these but a future log-format change shouldn't crash the pane.
    }
  }
  return lines
}

export async function downloadJobLogsZip(jobId: string): Promise<void> {
  const token = getToken()
  const headers: Record<string, string> = {}
  if (token) headers['Authorization'] = `Bearer ${token}`
  const url = `${API_BASE}/api/logs/${encodeURIComponent(jobId)}.zip`
  const resp = await fetch(url, { headers })
  if (!resp.ok) {
    throw new Error(`download logs failed: ${resp.status}`)
  }
  const blob = await resp.blob()
  const objectUrl = URL.createObjectURL(blob)
  try {
    const a = document.createElement('a')
    a.href = objectUrl
    a.download = `arm-logs-${jobId}.zip`
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
  } finally {
    URL.revokeObjectURL(objectUrl)
  }
}
