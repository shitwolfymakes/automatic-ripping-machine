<script lang="ts">
	import type { JobView } from '$lib/types/api.gen';
	import { abandonJob, deleteJob } from '$lib/api/jobs';
	import { isJobActive } from '$lib/utils/job-type';

	interface Props {
		job: JobView;
		onaction?: () => void;
		ondelete?: () => void;
		compact?: boolean;
	}

	let { job, onaction, ondelete, compact = false }: Props = $props();

	let loading = $state<string | null>(null);
	let feedback = $state<{ type: 'success' | 'error'; message: string } | null>(null);

	let active = $derived(isJobActive(job.status));
	// v3 terminal JobStatus members that a finished job can land in.
	const TERMINAL = new Set(['ripped', 'ripped_partial', 'ripped_awaiting_identify', 'abandoned', 'failed']);
	let canAbandon = $derived(active);
	let canDelete = $derived(TERMINAL.has(job.status));

	function clearFeedback() {
		setTimeout(() => (feedback = null), 3000);
	}

	function jobLabel(): string {
		return job.title || job.id;
	}

	async function handleAbandon() {
		if (!confirm(`Abandon job "${jobLabel()}"?`)) return;
		loading = 'abandon';
		feedback = null;
		try {
			await abandonJob(job.id);
			feedback = { type: 'success', message: 'Job abandoned' };
			onaction?.();
		} catch (e) {
			feedback = { type: 'error', message: e instanceof Error ? e.message : 'Failed to abandon' };
		} finally {
			loading = null;
			clearFeedback();
		}
	}

	async function handleDelete() {
		if (!confirm(`Delete job "${jobLabel()}"? This cannot be undone.`)) return;
		loading = 'delete';
		feedback = null;
		try {
			await deleteJob(job.id);
			if (ondelete) {
				ondelete();
				return;
			}
			feedback = { type: 'success', message: 'Job deleted' };
			onaction?.();
		} catch (e) {
			feedback = { type: 'error', message: e instanceof Error ? e.message : 'Failed to delete' };
		} finally {
			loading = null;
			clearFeedback();
		}
	}

</script>

{#if canAbandon || canDelete}
	<div class="cluster job-actions-row">
		{#if canAbandon}
			<button
				onclick={handleAbandon}
				disabled={loading !== null}
				data-compact={compact}
				class="job-actions-pill job-actions-pill-warning"
			>
				{loading === 'abandon' ? 'Abandoning...' : 'Abandon'}
			</button>
		{/if}
		{#if canDelete}
			<button
				onclick={handleDelete}
				disabled={loading !== null}
				data-compact={compact}
				class="job-actions-pill job-actions-pill-danger"
			>
				{loading === 'delete' ? 'Deleting...' : 'Delete'}
			</button>
		{/if}
		{#if feedback}
			<span class="job-actions-feedback" data-tone={feedback.type}>
				{feedback.message}
			</span>
		{/if}
	</div>
{/if}

<style>
	.job-actions-row { gap: 0.375rem; }
	/* the original was a filled soft pill (rounded-full, bg-*-100/text-*-700),
	   not .btn's outlined default nor .btn-danger/.btn-warning's outlined tone
	   look */
	.job-actions-pill { border: 0; border-radius: 9999px; padding: 0.375rem 0.75rem; font-size: 0.75rem; line-height: 1rem; font-weight: 500; cursor: pointer; transition: background-color var(--motion-fast) var(--ease); }
	/* compact: original was rounded px-2 py-0.5 (not rounded-full px-3 py-1.5);
	   Tailwind's unprefixed `rounded` is 0.25rem, matching neither radius token exactly */
	.job-actions-pill[data-compact="true"] { border-radius: 0.25rem; padding: 0.125rem 0.5rem; }
	.job-actions-pill:disabled { opacity: 0.5; cursor: not-allowed; }
	.job-actions-pill-warning { background: var(--color-warning-soft); color: var(--color-on-warning-soft); }
	.job-actions-pill-warning:hover { background: color-mix(in srgb, var(--color-warning-soft) 70%, var(--color-warning)); }
	/* the original also carried ring-1 ring-red-200 (a box-shadow ring, not
	   .btn's real border - same 30%-mix treatment as DiscReviewWidget's
	   Cancel button) */
	.job-actions-pill-danger { background: var(--color-danger-soft); color: var(--color-on-danger-soft); box-shadow: 0 0 0 1px color-mix(in srgb, var(--color-danger) 30%, transparent); }
	.job-actions-pill-danger:hover { background: color-mix(in srgb, var(--color-danger-soft) 70%, var(--color-danger)); }
	.job-actions-feedback { font-size: 0.75rem; line-height: 1rem; }
	.job-actions-feedback[data-tone="success"] { color: var(--color-success); }
	.job-actions-feedback[data-tone="error"] { color: var(--color-danger); }
</style>
