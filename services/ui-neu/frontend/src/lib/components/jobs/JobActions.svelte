<script lang="ts">
	import { errorMessage } from '$lib/utils/errors';
	import type { JobView } from '$lib/types/api.gen';
	import { abandonJob, deleteJob, ripAgain } from '$lib/api/jobs';
	import { isRipped } from '$lib/jobs/status-groups';
	import { onDestroy } from 'svelte';
	import { TimedFeedback } from '$lib/stores/timed-feedback.svelte';
	import ConfirmDialog from '$lib/components/shared/ConfirmDialog.svelte';

	interface Props {
		job: JobView;
		onaction?: () => void;
		ondelete?: () => void;
	}

	let { job, onaction, ondelete }: Props = $props();

	let loading = $state<string | null>(null);
	const feedback = new TimedFeedback(3000);
	onDestroy(() => feedback.dispose());
	// The destructive action waiting on its confirm dialog, if any.
	let confirming = $state<'abandon' | 'delete' | null>(null);

	let canAbandon = $derived(job.actions.can_abandon);
	let canDelete = $derived(job.actions.can_delete);
	// A ripped disc that the previously-ripped setting would hold or reject
	// on its next insert: let it through (or start the copy already held).
	let canRipAgain = $derived(isRipped(job.status));

	function jobLabel(): string {
		return job.title || job.id;
	}

	// Runs one action: the busy flag, the feedback line and its 3-second
	// clear. `act` sends the request and returns the success line, or null
	// when the action handed off and shows no line (a delete with ondelete).
	async function runAction(name: string, failed: string, act: () => Promise<string | null>): Promise<void> {
		loading = name;
		feedback.clear();
		try {
			const message = await act();
			if (message === null) return;
			feedback.show('success', message);
			onaction?.();
		} catch (e) {
			feedback.show('error', errorMessage(e, failed));
		} finally {
			loading = null;
		}
	}

	async function abandon() {
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

	async function remove() {
		await runAction('delete', 'Failed to delete', async () => {
			await deleteJob(job.id);
			if (ondelete) {
				ondelete();
				return null;
			}
			return 'Job deleted';
		});
	}

	// The confirm dialog's wording and the action it runs, per action.
	const CONFIRMS = {
		abandon: {
			title: 'Abandon job',
			message: (label: string) => `Abandon job "${label}"?`,
			confirmLabel: 'Abandon',
			run: abandon
		},
		delete: {
			title: 'Delete job',
			message: (label: string) => `Delete job "${label}"? This cannot be undone.`,
			confirmLabel: 'Delete',
			run: remove
		}
	};

	function confirmPending(kind: 'abandon' | 'delete') {
		confirming = null;
		CONFIRMS[kind].run();
	}
</script>

{#if canAbandon || canDelete || canRipAgain}
	<div class="cluster job-actions-row">
		{#if canRipAgain}
			<button
				type="button"
				onclick={handleRipAgain}
				disabled={loading !== null}
				class="btn btn-sm"
				title="Rip this disc again even though it was ripped before"
			>
				{loading === 'rip-again' ? 'Working...' : 'Rip again'}
			</button>
		{/if}
		{#if canAbandon}
			<button
				type="button"
				onclick={() => (confirming = 'abandon')}
				disabled={loading !== null}
				class="btn btn-sm btn-warning"
			>
				{loading === 'abandon' ? 'Abandoning...' : 'Abandon'}
			</button>
		{/if}
		{#if canDelete}
			<button
				type="button"
				onclick={() => (confirming = 'delete')}
				disabled={loading !== null}
				class="btn btn-sm btn-danger"
			>
				{loading === 'delete' ? 'Deleting...' : 'Delete'}
			</button>
		{/if}
		{#if feedback.current}
			<span class="job-actions-feedback" data-tone={feedback.current.type}>
				{feedback.current.message}
			</span>
		{/if}
	</div>
{/if}

{#if confirming}
	{@const kind = confirming}
	<ConfirmDialog
		open
		title={CONFIRMS[kind].title}
		message={CONFIRMS[kind].message(jobLabel())}
		confirmLabel={CONFIRMS[kind].confirmLabel}
		variant="danger"
		onconfirm={() => confirmPending(kind)}
		oncancel={() => (confirming = null)}
	/>
{/if}

<style>
	.job-actions-row {
		gap: 0.375rem;
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
