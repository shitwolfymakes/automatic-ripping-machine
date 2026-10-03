export function timeAgo(dateString: string | null | undefined): string {
	if (!dateString) return 'N/A';
	const date = new Date(dateString);
	const now = new Date();
	const seconds = Math.max(0, Math.floor((now.getTime() - date.getTime()) / 1000));

	if (seconds < 60) return `${seconds}s ago`;
	const minutes = Math.floor(seconds / 60);
	if (minutes < 60) return `${minutes}m ago`;
	const hours = Math.floor(minutes / 60);
	if (hours < 24) return `${hours}h ago`;
	const days = Math.floor(hours / 24);
	return `${days}d ago`;
}

export function formatBytes(bytes: number): string {
	if (bytes === 0) return '0 B';
	const k = 1024;
	const sizes = ['B', 'KB', 'MB', 'GB', 'TB'];
	const i = Math.floor(Math.log(bytes) / Math.log(k));
	return `${parseFloat((bytes / Math.pow(k, i)).toFixed(1))} ${sizes[i]}`;
}

export function formatDateTime(dateString: string | null | undefined): string {
	if (!dateString) return 'N/A';
	return new Date(dateString).toLocaleString();
}

export function elapsedTime(startTime: string | null | undefined): string {
	if (!startTime) return 'N/A';
	const start = new Date(startTime);
	const now = new Date();
	const totalSeconds = Math.max(0, Math.floor((now.getTime() - start.getTime()) / 1000));

	const hours = Math.floor(totalSeconds / 3600);
	const minutes = Math.floor((totalSeconds % 3600) / 60);
	const seconds = totalSeconds % 60;

	if (hours > 0) return `${hours}h ${minutes}m`;
	if (minutes > 0) return `${minutes}m ${seconds}s`;
	return `${seconds}s`;
}

/**
 * Estimate time remaining for an in-flight job.
 * Returns null when an ETA can't be reasonably computed (just started,
 * already done, no progress signal); the caller renders an em-dash.
 *
 * The 30s elapsed threshold smooths the noisy first-percent jitter
 * that MakeMKV/abcde produce during drive-spin and warm-up.
 * Capped at 24h+ to avoid printing absurd estimates from sub-1%
 * progress values that haven't yet stabilised.
 */
export function etaTime(startTime: string | null | undefined, progressPct: number | null | undefined): string | null {
	if (!startTime || progressPct == null) return null;
	if (progressPct <= 0 || progressPct >= 100) return null;
	const start = new Date(startTime);
	const elapsedSec = (Date.now() - start.getTime()) / 1000;
	if (elapsedSec < 30) return null;
	const remainingSec = (elapsedSec * (100 - progressPct)) / progressPct;
	if (remainingSec >= 24 * 3600) return '24h+';
	const h = Math.floor(remainingSec / 3600);
	const m = Math.floor((remainingSec % 3600) / 60);
	const s = Math.floor(remainingSec % 60);
	if (h > 0) return `${h}h ${m}m`;
	if (m > 0) return `${m}m ${s}s`;
	return `${s}s`;
}

/**
 * Map a status to a themeable CSS variable reference suitable for inline
 * `style="background: ${statusAccentVar(status)}"` use. Falls back to the
 * primary brand color so unrecognized statuses still pick up theme tinting.
 *
 * Accepts three vocabularies (see the generated `$lib/types/api.gen`):
 *   - v3 JobStatus values (created ... failed), plus the effective statuses
 *     transcoding / complete / transcode_failed from effectiveJobStatus()
 *   - transcode task and track statuses (queued, in_progress, done, cancelled)
 *   - application statuses (waiting_identify, running, done_partial)
 */
export function statusAccentVar(status: string | null | undefined): string {
	switch (status?.toLowerCase()) {
		case 'created':
		case 'preparing': // ISO rip scanning / unpacking its image, no job yet
			return 'var(--color-status-scanning)';
		case 'identified': // queued to rip
		case 'ripping':
			return 'var(--color-status-ripping)';
		case 'transcoding':
			return 'var(--color-status-transcoding)';
		case 'complete':
		case 'done':
		case 'ripped':
			return 'var(--color-status-success)';
		case 'failed':
		case 'transcode_failed':
		case 'done_partial':
			return 'var(--color-status-error)';
		case 'awaiting_user_id':
		case 'awaiting_review': // held for the timed review gate
		case 'ripped_partial':
		case 'ripped_awaiting_identify':
		case 'waiting_identify':
			return 'var(--color-status-waiting)';
		default: // incl. abandoned, queued, in_progress, running, cancelled: neutral
			return 'var(--color-primary)';
	}
}

/**
 * Map a status string to a CSS class. Accepts three vocabularies (see the
 * generated `$lib/types/api.gen`):
 *   - v3 JobStatus values (created ... failed), plus the effective statuses
 *     transcoding / complete / transcode_failed from effectiveJobStatus()
 *   - transcode task and track statuses (queued, in_progress, done, cancelled)
 *   - application statuses (waiting_identify, running, done_partial)
 */
export function statusColor(status: string | null | undefined): string {
	switch (status?.toLowerCase()) {
		case 'created': // disc inserted, not yet identified
		case 'preparing': // ISO rip scanning / unpacking its image, no job yet
			return 'status-scanning';
		case 'awaiting_user_id': // needs manual identification
		case 'awaiting_review': // held for the timed review gate
		case 'ripped_awaiting_identify': // ripped, still needs ID
		case 'waiting_identify':
		case 'ripped_partial': // rip finished with some titles failed
			return 'status-warning';
		case 'identified': // identified, queued/ready to rip
		case 'ripping':
			return 'status-active';
		case 'transcoding':
			return 'status-processing';
		case 'complete': // effectiveJobStatus() rollup for a fully-transcoded job
		case 'done': // transcode task terminal success
		case 'ripped': // rip complete (terminal)
			return 'status-success';
		case 'failed':
		case 'transcode_failed': // ripped OK but some/all tracks failed to transcode
		case 'done_partial': // transcode finished with some titles failed
			return 'status-error';
		default: // incl. abandoned, queued, in_progress, running, cancelled
			return 'status-unknown';
	}
}

const STATUS_LABELS: Record<string, string> = {
	// v3 JobStatus values (packages/arm_common enums.py)
	created: 'Created',
	awaiting_user_id: 'Awaiting ID',
	awaiting_review: 'Ready: review',
	identified: 'Identified',
	ripping: 'Ripping',
	ripped: 'Ripped',
	ripped_partial: 'Ripped (partial)',
	ripped_awaiting_identify: 'Ripped (awaiting ID)',
	abandoned: 'Abandoned',
	failed: 'Failed',
	// effective statuses (effectiveJobStatus)
	transcoding: 'Transcoding',
	complete: 'Complete',
	transcode_failed: 'Transcode failed',
	// task / track / application statuses
	queued: 'Queued',
	in_progress: 'In Progress',
	done: 'Done',
	cancelled: 'Cancelled',
	waiting_identify: 'Waiting to identify',
	running: 'Running',
	done_partial: 'Done (partial)'
};

export function statusLabel(status: string | null | undefined): string {
	if (!status) return 'Unknown';
	const key = status.toLowerCase();
	// Unmapped statuses (future additions) humanize instead of leaking raw:
	// "some_new_state" → "Some New State", never lowercase verbatim.
	return (
		STATUS_LABELS[key] ??
		key
			.split('_')
			.map((w) => (w ? w[0].toUpperCase() + w.slice(1) : w))
			.join(' ')
	);
}
