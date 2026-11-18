import { formatRemaining } from '$lib/utils/format';

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
	return formatRemaining((elapsedSec * (100 - progressPct)) / progressPct);
}

/**
 * The words for a rip's live progress stage: the two copy stages get plain
 * words and any other stage is shown as the ripper named it.
 */
export function formatRipStage(stage: string): string {
	if (stage === 'scratch-to-media') return 'Copying to shared storage';
	if (stage === 'work-to-completed') return 'Moving to completed';
	return stage;
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
