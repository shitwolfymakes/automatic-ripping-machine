import type { JobLogFileView } from '$lib/types/api.gen';
import { ApiError, apiFetch, getToken, notifyUnauthorized } from './client';

// v3 logs are JOB-ID scoped. The screen browses jobs (GET /api/jobs) and views
// one job's aggregated log via GET /api/logs/{job_id} (NDJSON; every line tagged
// with that job_id, incl. transcode). The bug-report zip is GET /api/logs/{job_id}.zip.
// One-shot snapshot read (no live follow).

export interface LogEntry {
	timestamp?: string | null;
	level: string;
	logger: string;
	event: string;
	job_id?: number | string | null;
	label?: string | null;
	service: string;
}

/**
 * Parse one raw backend log record ({ts, level, service, job_id, track_id,
 * session_application_id, msg, extra:{logger,...}}) into a LogEntry. Exported
 * so the WS live-tail path (jobLog store) can reuse the same parsing as the
 * one-shot NDJSON fetch below.
 */
export function toLogEntry(raw: Record<string, unknown>): LogEntry {
	const extra = (raw.extra ?? {}) as Record<string, unknown>;
	const str = (v: unknown): string => (typeof v === 'string' ? v : v == null ? '' : String(v));
	return {
		timestamp: typeof raw.ts === 'string' ? raw.ts : null,
		level: str(raw.level),
		logger: str(extra.logger ?? raw.service),
		event: str(raw.msg),
		job_id: (raw.job_id as string | number | null | undefined) ?? null,
		label: typeof extra.label === 'string' ? extra.label : null,
		service: str(raw.service)
	};
}

function parseNdjsonLine(line: string): Record<string, unknown> | null {
	const trimmed = line.trim();
	if (!trimmed) return null;
	let raw: Record<string, unknown>;
	try {
		raw = JSON.parse(trimmed) as Record<string, unknown>;
	} catch {
		return null; // skip a mangled line rather than blank the whole view
	}
	if (raw === null || typeof raw !== 'object') return null;
	return raw;
}

/**
 * Parse an NDJSON body into log entries, in order. Blank / unparseable lines
 * are skipped defensively (the backend reads with errors="replace" and can
 * emit a mangled line).
 */
function parseNdjson(body: string): LogEntry[] {
	const entries: LogEntry[] = [];
	for (const line of body.split('\n')) {
		const raw = parseNdjsonLine(line);
		if (raw) entries.push(toLogEntry(raw));
	}
	return entries;
}

/**
 * Fetch one job's aggregated log as parsed NDJSON entries.
 * The endpoint is JWT-gated and returns text/NDJSON (not JSON), so this uses a
 * raw fetch with a manual bearer header rather than apiFetch (which assumes JSON).
 */
export async function fetchJobLog(jobId: string, limit?: number): Promise<LogEntry[]> {
	const qs = limit != null ? `?limit=${limit}` : '';
	const headers: Record<string, string> = {};
	const token = getToken();
	if (token) headers['Authorization'] = `Bearer ${token}`;
	const res = await fetch(`/api/logs/${encodeURIComponent(jobId)}${qs}`, { headers });
	if (res.status === 401) {
		notifyUnauthorized();
		throw new ApiError(401, 'API 401: Unauthorized', null);
	}
	if (!res.ok) {
		throw new ApiError(res.status, `API ${res.status}: ${res.statusText}`, null);
	}
	return parseNdjson(await res.text());
}

/** Per-job bug-report zip URL (used by a download link). */
export function jobLogDownloadUrl(jobId: string): string {
	return `/api/logs/${encodeURIComponent(jobId)}.zip`;
}

/** Index of per-job log files (size + last-modified), newest first. */
export function fetchJobLogIndex(): Promise<JobLogFileView[]> {
	return apiFetch<JobLogFileView[]>('/api/logs');
}
