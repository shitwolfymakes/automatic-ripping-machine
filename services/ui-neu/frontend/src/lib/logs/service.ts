// Classifies a raw log record's `service` field (arm-backend,
// arm-ripper-<serial>, arm-transcode-<task>) into the coarse group the
// JobLogPanel filters and colors by.

export type LogService = 'backend' | 'ripper' | 'transcode' | 'other';

export function logService(service: string): LogService {
	if (service === 'arm-backend') return 'backend';
	if (/^arm-ripper/.test(service)) return 'ripper';
	if (/^arm-transcode/.test(service)) return 'transcode';
	return 'other';
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
