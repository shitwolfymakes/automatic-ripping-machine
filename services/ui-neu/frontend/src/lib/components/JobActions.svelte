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

	let btnBase = $derived(
		compact
			? 'rounded px-2 py-0.5 text-xs font-medium disabled:opacity-50 transition-colors'
			: 'rounded-full px-3 py-1.5 text-xs font-medium disabled:opacity-50 transition-colors'
	);
</script>

{#if canAbandon || canDelete}
	<div class="flex flex-wrap items-center gap-1.5">
		{#if canAbandon}
			<button
				onclick={handleAbandon}
				disabled={loading !== null}
				class="{btnBase} bg-yellow-100 text-yellow-700 hover:bg-yellow-200 dark:bg-yellow-900/30 dark:text-yellow-400 dark:hover:bg-yellow-900/50"
			>
				{loading === 'abandon' ? 'Abandoning...' : 'Abandon'}
			</button>
		{/if}
		{#if canDelete}
			<button
				onclick={handleDelete}
				disabled={loading !== null}
				class="{btnBase} bg-red-100 text-red-700 ring-1 ring-red-200 hover:bg-red-200 dark:bg-red-900/30 dark:text-red-400 dark:ring-red-800 dark:hover:bg-red-900/50"
			>
				{loading === 'delete' ? 'Deleting...' : 'Delete'}
			</button>
		{/if}
		{#if feedback}
			<span class="text-xs {feedback.type === 'success' ? 'text-green-600 dark:text-green-400' : 'text-red-600 dark:text-red-400'}">
				{feedback.message}
			</span>
		{/if}
	</div>
{/if}
