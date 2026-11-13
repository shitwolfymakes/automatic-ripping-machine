<script lang="ts">
	import type { DriveView as Drive } from '$lib/types/api.gen';
	import { updateDrive } from '$lib/api/drives';
	import { driveStatusLabel, isDriveDetached, isRipperOfflinePresent } from '$lib/drives/drives';
	import StatusBadge from '../StatusBadge.svelte';

	interface Props {
		/** The drive this header shows. */
		drive: Drive;
		/** Called after a rename that the drive list should refresh for. */
		onupdate?: () => void | Promise<void>;
	}

	let { drive, onupdate }: Props = $props();

	const statusText = $derived(driveStatusLabel(drive));
	const isDetached = $derived(isDriveDetached(drive));
	const isError = $derived(drive.status === 'error');
	const isOfflinePresent = $derived(isRipperOfflinePresent(drive));

	let editing = $state(false);
	let editName = $state('');
	let saving = $state(false);

	function startEdit() {
		editName = drive.display_name || '';
		editing = true;
	}

	function cancelEdit() {
		editing = false;
	}

	async function saveEdit() {
		saving = true;
		try {
			await updateDrive(drive.id, { display_name: editName });
			editing = false;
			onupdate?.();
		} catch {
			// keep edit mode open on failure
		} finally {
			saving = false;
		}
	}

	function onKeydown(e: KeyboardEvent) {
		if (e.key === 'Enter') saveEdit();
		if (e.key === 'Escape') cancelEdit();
	}
</script>

<div class="mb-1 flex items-center justify-between">
	<div class="flex min-w-0 items-center gap-1.5">
		<h3 class="truncate drive-card-title">
			{drive.display_name || drive.device_path || `Drive ${drive.id}`}
		</h3>
		{#if isError}
			<span class="flex-shrink-0 drive-card-status-error" title={statusText}>{statusText}</span>
		{:else if isDetached}
			<span class="flex-shrink-0 badge badge-warning badge-sm drive-card-status-pill">{statusText}</span>
		{:else if isOfflinePresent}
			<span class="flex-shrink-0 badge badge-warning badge-sm drive-card-status-pill" data-testid="drive-status-label"
				>{statusText}</span
			>
		{:else if !editing}
			<button onclick={startEdit} class="btn btn-link btn-sm flex-shrink-0">Rename</button>
		{/if}
	</div>
	{#if drive.current_job}
		<StatusBadge status={drive.current_job.status} />
	{:else}
		<span class="flex-shrink-0 drive-card-idle">Idle</span>
	{/if}
</div>

<!-- Name editing -->
{#if editing}
	<div class="mb-2 flex items-center gap-2">
		<input
			type="text"
			bind:value={editName}
			onkeydown={onKeydown}
			class="field-control drive-card-edit-input"
			disabled={saving}
		/>
		<button onclick={saveEdit} disabled={saving} class="btn btn-primary btn-sm">Save</button>
		<button onclick={cancelEdit} disabled={saving} class="btn btn-ghost btn-sm">Cancel</button>
	</div>
{/if}

<style>
	.drive-card-title {
		font-weight: 600;
		font-size: 0.875rem;
		color: var(--color-text);
	}
	/* text-xs text-gray-400 - a plain inline span in a flex row, not
	   panel-hint's block-level note (whose own margin-top would misalign
	   it against its row siblings) or its muted (not faint) color. */
	.drive-card-idle {
		font-size: 0.75rem;
		line-height: 1rem;
		color: var(--color-text-faint);
	}
	.drive-card-status-error {
		font-size: 0.625rem;
		font-weight: 500;
		color: var(--color-danger);
	}
	/* badge-warning is a solid fill; this pill was always a soft amber tint
	   (bg-amber-500/20 text-amber-700), closer to alert-warning's tone. */
	.drive-card-status-pill {
		background: var(--color-warning-soft);
		color: var(--color-on-warning-soft);
	}
	.drive-card-edit-input {
		font-size: 0.875rem;
		font-weight: 600;
	}
</style>
