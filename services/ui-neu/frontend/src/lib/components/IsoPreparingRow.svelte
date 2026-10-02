<script lang="ts">
	import type { IsoPreparing } from '$lib/api/dashboard';
	import IsoSourceChip from './IsoSourceChip.svelte';
	import ProgressBar from './ProgressBar.svelte';
	import StatusBadge from './StatusBadge.svelte';
	import { isAdmin } from '$lib/stores/auth';
	import { cancelIsoRip } from '$lib/api/iso';
	import { addToast } from '$lib/stores/toast.svelte';

	/**
	 * An ISO rip before its job exists: the ripper is scanning the image, or
	 * unpacking one MakeMKV can't open directly (which can take half an hour
	 * for a Blu-ray on a network share). Once identify creates the job, the
	 * job's own ActiveJobRow replaces this row.
	 */
	interface Props {
		prepare: IsoPreparing;
	}

	let { prepare }: Props = $props();

	const PHASE_LABELS: Record<string, string> = {
		scanning: 'Scanning image',
		extracting: 'Unpacking image'
	};

	let cancelling = $state(false);
	let phaseLabel = $derived(PHASE_LABELS[prepare.phase] ?? prepare.phase);
	const accentVar = 'var(--color-status-scanning)';

	async function handleCancel() {
		cancelling = true;
		try {
			await cancelIsoRip(prepare.drive_id);
		} catch (e) {
			addToast({ tone: 'error', title: 'Cancel failed', body: e instanceof Error ? e.message : 'Unknown error' });
		} finally {
			cancelling = false;
		}
	}
</script>

<div class="card card-status iso-preparing-row" data-status="scanning" data-source="iso">
	<div class="iso-preparing-row-head flex items-center gap-3">
		<span class="shrink-0"><IsoSourceChip name={prepare.iso_name} /></span>
		<span class="shrink-0"><StatusBadge status="preparing" /></span>
		<span class="min-w-0 truncate iso-preparing-row-phase">{phaseLabel}</span>
		<span class="flex-1"></span>
		{#if $isAdmin}
			<button
				onclick={handleCancel}
				disabled={cancelling}
				class="btn btn-danger btn-sm shrink-0"
				title="Cancel the rip and remove the virtual drive"
			>
				{cancelling ? 'Cancelling...' : 'Cancel'}
			</button>
		{/if}
	</div>

	<div class="iso-preparing-row-progress">
		{#if prepare.progress_pct != null}
			<ProgressBar value={prepare.progress_pct} colorVar={accentVar} />
		{:else}
			<!-- data-indeterminate: the progress vocabulary's state hook. -->
			<div data-indeterminate="true" class="iso-preparing-row-indeterminate-track">
				<div class="iso-preparing-row-indeterminate-fill" style:--jt-progress-color={accentVar}></div>
			</div>
		{/if}
		{#if prepare.current_file}
			<div class="truncate iso-preparing-row-file" title={prepare.current_file}>{prepare.current_file}</div>
		{/if}
	</div>
</div>

<style>
	.iso-preparing-row-head {
		padding: 0.625rem 1rem 0;
	}
	.iso-preparing-row-phase {
		font-size: 0.875rem;
		line-height: 1.25rem;
		font-weight: 600;
		color: var(--color-text);
	}
	.iso-preparing-row-progress {
		margin-top: 0.5rem;
		border-top: 1px solid var(--color-border);
		padding: 0.625rem 1rem;
	}
	.iso-preparing-row-file {
		margin-top: 0.25rem;
		font-size: 0.75rem;
		line-height: 1rem;
		color: var(--color-text-muted);
		font-family: var(--font-mono, monospace);
	}
	.iso-preparing-row-indeterminate-track {
		height: 0.625rem;
		overflow: hidden;
		border-radius: 9999px;
		background: var(--color-primary-tint-3);
	}
	.iso-preparing-row-indeterminate-fill {
		height: 100%;
		width: 33.3333%;
		border-radius: 9999px;
		background: var(--jt-progress-color);
		opacity: 0.6;
		animation: var(--animate-indeterminate);
	}
</style>
