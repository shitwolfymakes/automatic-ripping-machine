<script lang="ts">
	import { errorMessage } from '$lib/utils/errors';
	import type { JobView } from '$lib/types/api.gen';
	import { abandonJob, deleteJob, ripAgain } from '$lib/api/jobs';
	import { isRipped } from '$lib/jobs/status-groups';

	interface Props {
		job: JobView;
		onaction?: () => void;
		ondelete?: () => void;
		compact?: boolean;
	}

	let { job, onaction, ondelete, compact = false }: Props = $props();

	let loading = $state<string | null>(null);
	let feedback = $state<{ type: 'success' | 'error'; message: string } | null>(null);

	let canAbandon = $derived(job.actions.can_abandon);
	let canDelete = $derived(job.actions.can_delete);
	// A ripped disc that the previously-ripped setting would hold or reject
	// on its next insert: let it through (or start the copy already held).
	let canRipAgain = $derived(isRipped(job.status));

	function clearFeedback() {
		setTimeout(() => (feedback = null), 3000);
	}

	function jobLabel(): string {
		return job.title || job.id;
	}

	// Runs one action: the busy flag, the feedback line and its 3-second
	// clear. `act` sends the request and returns the success line, or null
	// when the action handed off and shows no line (a delete with ondelete).
	async function runAction(name: string, failed: string, act: () => Promise<string | null>): Promise<void> {
		loading = name;
		feedback = null;
		try {
			const message = await act();
			if (message === null) return;
			feedback = { type: 'success', message };
			onaction?.();
		} catch (e) {
			feedback = { type: 'error', message: errorMessage(e, failed) };
		} finally {
			loading = null;
			clearFeedback();
		}
	}

	async function handleAbandon() {
		if (!confirm(`Abandon job "${jobLabel()}"?`)) return;
		await runAction('abandon', 'Failed to abandon', async () => {
			await abandonJob(job.id);
			return 'Job abandoned';
		});
	}

	async function handleRipAgain() {
		await runAction('rip-again', 'Failed to rip again', async () => {
			const out = await ripAgain(job.id);
			return out.started_job_id
				? 'Started ripping the copy waiting in the drive'
				: 'The next time this disc goes in, ARM rips it again';
		});
	}

	async function handleDelete() {
		if (!confirm(`Delete job "${jobLabel()}"? This cannot be undone.`)) return;
		await runAction('delete', 'Failed to delete', async () => {
			await deleteJob(job.id);
			if (ondelete) {
				ondelete();
				return null;
			}
			return 'Job deleted';
		});
	}
</script>

{#if canAbandon || canDelete || canRipAgain}
	<div class="cluster job-actions-row">
		{#if canRipAgain}
			<button
				onclick={handleRipAgain}
				disabled={loading !== null}
				data-compact={compact}
				class="job-actions-pill job-actions-pill-neutral"
				title="Rip this disc again even though it was ripped before"
			>
				{loading === 'rip-again' ? 'Working...' : 'Rip again'}
			</button>
		{/if}
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
	.job-actions-row {
		gap: 0.375rem;
	}
	/* the original was a filled soft pill (rounded-full, bg-*-100/text-*-700),
	   not .btn's outlined default nor .btn-danger/.btn-warning's outlined tone
	   look */
	.job-actions-pill {
		border: 0;
		border-radius: 9999px;
		padding: 0.375rem 0.75rem;
		font-size: 0.75rem;
		line-height: 1rem;
		font-weight: 500;
		cursor: pointer;
		transition: background-color var(--motion-fast) var(--ease);
	}
	/* compact: original was rounded px-2 py-0.5 (not rounded-full px-3 py-1.5);
	   Tailwind's unprefixed `rounded` is 0.25rem, matching neither radius token exactly */
	.job-actions-pill[data-compact='true'] {
		border-radius: 0.25rem;
		padding: 0.125rem 0.5rem;
	}
	.job-actions-pill:disabled {
		opacity: 0.5;
		cursor: not-allowed;
	}
	.job-actions-pill-neutral {
		background: var(--color-surface-raised);
		color: var(--color-text);
		box-shadow: 0 0 0 1px var(--color-border);
	}
	.job-actions-pill-neutral:hover {
		background: color-mix(in srgb, var(--color-surface-raised) 85%, var(--color-text));
	}
	.job-actions-pill-warning {
		background: var(--color-warning-soft);
		color: var(--color-on-warning-soft);
	}
	.job-actions-pill-warning:hover {
		background: color-mix(in srgb, var(--color-warning-soft) 70%, var(--color-warning));
	}
	/* the original also carried ring-1 ring-red-200 (a box-shadow ring, not
	   .btn's real border - same 30%-mix treatment as DiscReviewWidget's
	   Cancel button) */
	.job-actions-pill-danger {
		background: var(--color-danger-soft);
		color: var(--color-on-danger-soft);
		box-shadow: 0 0 0 1px color-mix(in srgb, var(--color-danger) 30%, transparent);
	}
	.job-actions-pill-danger:hover {
		background: color-mix(in srgb, var(--color-danger-soft) 70%, var(--color-danger));
	}
	.job-actions-feedback {
		font-size: 0.75rem;
		line-height: 1rem;
	}
	.job-actions-feedback[data-tone='success'] {
		color: var(--color-success);
	}
	.job-actions-feedback[data-tone='error'] {
		color: var(--color-danger);
	}
</style>
