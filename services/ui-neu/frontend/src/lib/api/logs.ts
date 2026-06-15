import { notAvailable } from './_stub';

// v3 logs are JOB-ID scoped (GET /api/logs/{job_id}, /{job_id}.zip), not
// filename-based. The BFF's filename-based log browser + transcoder log feed
// have no v3 equivalent (MISSING). The Logs screen and the inline log feeds are
// dormant, so these stubs reject before any fetch.
//
// The shapes the (dormant) log viewers read are declared locally here and
// re-exported; api.gen no longer carries LogFileSchema / LogContentResponse /
// StructuredLogResponse / LogEntrySchema.

export interface LogFile {
	filename: string;
	size: number;
	modified: string;
}

export interface LogContent {
	content: string;
	filename?: string;
}

export interface LogEntry {
	timestamp?: string | null;
	level: string;
	logger: string;
	event: string;
	job_id?: number | string | null;
	label?: string | null;
}

export interface StructuredLogContent {
	entries: LogEntry[];
	filename?: string;
}

// Re-exported under the names the components import.
export type { LogFile as LogFileSchema, LogContent as LogContentResponse };
export type { StructuredLogContent as StructuredLogResponse, LogEntry as LogEntrySchema };

export async function fetchLogs(): Promise<LogFile[]> {
	notAvailable('Log file listing');
}

export async function fetchLogContent(
	_filename: string,
	_mode: 'tail' | 'full' = 'tail',
	_lines: number = 100
): Promise<LogContent> {
	notAvailable('Log content');
}

export async function fetchStructuredLogContent(
	_filename: string,
	_mode: 'tail' | 'full' = 'tail',
	_lines: number = 100,
	_level?: string,
	_search?: string
): Promise<StructuredLogContent> {
	notAvailable('Structured log content');
}

export async function fetchTranscoderLogs(): Promise<LogFile[]> {
	notAvailable('Transcoder log listing');
}

export async function fetchTranscoderLogContent(
	_filename: string,
	_mode: 'tail' | 'full' = 'tail',
	_lines: number = 100
): Promise<LogContent> {
	notAvailable('Transcoder log content');
}

export async function fetchStructuredTranscoderLogContent(
	_filename: string,
	_mode: 'tail' | 'full' = 'tail',
	_lines: number = 100,
	_level?: string,
	_search?: string
): Promise<StructuredLogContent> {
	notAvailable('Structured transcoder log content');
}

export async function deleteLog(
	_filename: string
): Promise<{ success: boolean; filename: string }> {
	notAvailable('Log delete');
}

// Pure URL builder — kept as a string so the (dormant) download links compile.
export function logDownloadUrl(filename: string): string {
	return `/api/logs/${encodeURIComponent(filename)}/download`;
}

export async function fetchTranscoderLogForArmJob(_armJobId: number): Promise<{
	found: boolean;
	logfile?: string;
	transcoder_job_id?: number;
	status?: string;
	phase?: string | null;
	progress?: number | null;
	current_fps?: number | null;
}> {
	notAvailable('Transcoder log for ARM job');
}
