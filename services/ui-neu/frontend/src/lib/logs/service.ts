// Groups a log line by pipeline stage for the job log's filter and colour:
// a milestone by the stage its event names (the backend writes the track and
// transcode milestones), any other line by the service that wrote it
// (arm-backend, arm-ripper-<serial>, arm-transcode-<task>).

export type LogService = 'backend' | 'ripper' | 'transcode' | 'other';

export function logService(service: string): LogService {
	if (service === 'arm-backend') return 'backend';
	if (/^arm-ripper/.test(service)) return 'ripper';
	if (/^arm-transcode/.test(service)) return 'transcode';
	return 'other';
}

// A milestone event's first segment, mapped to its stage.
const EVENT_STAGES: Record<string, LogService> = {
	identify: 'backend',
	episodes: 'backend',
	rip: 'ripper',
	track: 'ripper',
	title: 'ripper',
	session: 'transcode',
	transcode: 'transcode'
};

export function entryGroup(entry: { service: string; event: string | null }): LogService {
	const stage = entry.event ? EVENT_STAGES[entry.event.split('.')[0]] : undefined;
	return stage ?? logService(entry.service);
}

const LABELS: Record<LogService, string> = {
	backend: 'Backend',
	ripper: 'Ripper',
	transcode: 'Transcode',
	other: 'Other'
};

export function serviceLabel(s: LogService): string {
	return LABELS[s];
}
