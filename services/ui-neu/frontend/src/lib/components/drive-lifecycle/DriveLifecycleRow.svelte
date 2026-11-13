<script lang="ts">
	// One drive in the lifecycle lists, with its identity, its Ignore or
	// Un-ignore and Enroll buttons, and its enroll progress or failure.
	import type { DriveView } from '$lib/types/api.gen';
	import { connectionLabel, driveTitle, mediaLabel, serialLabel } from '$lib/drives/drives';
	import { formatDateTime } from '$lib/utils/format';
	import Glyph from '$lib/components/Glyph.svelte';
	import StatusStrip from '$lib/components/StatusStrip.svelte';

	interface Props {
		/** The drive this row shows. */
		drive: DriveView;
		/** True for a row in the Ignored list. */
		ignored: boolean;
		/** The drive was not there at first render; the row shows it only when
		 *  not ignored. */
		isNew: boolean;
		/** The action running on this drive. */
		busy: 'enroll' | 'other' | undefined;
		/** The last action's error on this drive. */
		error: string | undefined;
		/** Set when enrolling can't work right now; disables Enroll. */
		enrollDisabledReason: string | null;
		/** Enroll, or Retry after a failure. */
		onenroll: () => void;
		/** Ignore on a detected row, Un-ignore on an ignored one. */
		ontoggleignore: () => void;
	}
	let { drive, ignored, isNew, busy, error, enrollDisabledReason, onenroll, ontoggleignore }: Props = $props();

	const serial = $derived(serialLabel(drive));
	const conn = $derived(connectionLabel(drive));
	const failure = $derived(error ?? (ignored ? null : drive.last_error));
	// The backend refuses to enroll an unplugged drive (409), so don't offer it.
	const absent = $derived(drive.present === false);
</script>

<div
	data-testid={`${ignored ? 'ignored' : 'detected'}-row-${drive.id}`}
	class="drive-lifecycle-lists-row"
	data-new={!ignored && isNew}
	data-failed={!!failure}
>
	<div class="drive-lifecycle-lists-head">
		<span class="drive-lifecycle-lists-icon" aria-hidden="true"><Glyph name="hard-drive" class="h-5 w-5" /></span>
		<div class="drive-lifecycle-lists-main">
			<div class="drive-lifecycle-lists-title-row">
				<span class="drive-lifecycle-lists-name">{driveTitle(drive)}</span>
				{#if !ignored && isNew}<span class="badge badge-sm badge-info">New</span>{/if}
			</div>
			<code class="mono drive-lifecycle-lists-path"
				>{drive.device_path}{drive.by_id_name ? `  ${drive.by_id_name}` : ''}</code
			>
			<div class="cluster drive-lifecycle-lists-chips">
				{#if conn}<span class="chip chip-sm">{conn}</span>{/if}
				<span class="chip chip-sm"><Glyph name="disc-3" class="h-3 w-3" />{mediaLabel(drive)}</span>
				<span class="drive-lifecycle-lists-serial" data-warn={serial.warn}>{serial.text}</span>
				<span class="drive-lifecycle-lists-seen">{drive.last_seen_at ? formatDateTime(drive.last_seen_at) : '-'}</span>
			</div>
		</div>
		<span class="drive-lifecycle-lists-actions">
			{#if ignored}
				<button
					data-testid={`unignore-${drive.id}`}
					disabled={!!busy}
					onclick={() => ontoggleignore()}
					class="btn btn-sm">Un-ignore</button
				>
			{:else}
				<button data-testid={`ignore-${drive.id}`} disabled={!!busy} onclick={() => ontoggleignore()} class="btn btn-sm"
					>Ignore</button
				>
			{/if}
			<button
				data-testid={`enroll-${drive.id}`}
				disabled={!!busy || !!enrollDisabledReason || absent}
				title={absent ? 'Not connected; plug the drive in to enroll it' : undefined}
				onclick={() => onenroll()}
				class="btn btn-primary btn-sm"
			>
				{#if failure && !ignored}<Glyph name="refresh" class="h-3.5 w-3.5" /> Retry{:else}Enroll{/if}
			</button>
		</span>
	</div>
	{#if busy === 'enroll'}
		<StatusStrip tone="busy" title="Starting ripper..." detail="Usually under 10 seconds" progress />
	{:else if failure}
		<div data-testid={`lifecycle-error-${drive.id}`}>
			<StatusStrip
				tone="danger"
				title="The ripper for this drive didn't start."
				detail="Other drives are not affected."
				message={failure}
			/>
		</div>
	{:else if absent}
		<div data-testid={`not-connected-${drive.id}`}>
			<StatusStrip tone="muted" title="Not connected" detail="Plug the drive in to enroll it." />
		</div>
	{:else if !ignored}
		<StatusStrip tone="muted" title="Not enrolled" detail="ARM leaves this drive alone until you enroll it." />
	{/if}
</div>

<style>
	.drive-lifecycle-lists-row {
		display: grid;
		gap: 0.75rem;
		border: 1px solid var(--color-border);
		border-radius: var(--radius-lg);
		padding: 0.875rem 1rem;
		font-size: 0.875rem;
	}
	.drive-lifecycle-lists-row[data-new='true'] {
		border-color: var(--color-primary);
		background: var(--color-primary-tint-1);
		animation: drive-lifecycle-lists-new 1.6s ease-out 1;
	}
	.drive-lifecycle-lists-row[data-failed='true'] {
		border-color: var(--color-danger);
	}
	@keyframes drive-lifecycle-lists-new {
		from {
			box-shadow: 0 0 0 6px var(--color-primary-tint-3);
		}
		to {
			box-shadow: 0 0 0 0 transparent;
		}
	}
	@media (prefers-reduced-motion: reduce) {
		.drive-lifecycle-lists-row[data-new='true'] {
			animation: none;
		}
	}
	.drive-lifecycle-lists-head {
		display: flex;
		align-items: flex-start;
		gap: 0.75rem;
	}
	.drive-lifecycle-lists-icon {
		flex: none;
		display: grid;
		place-items: center;
		width: 2.25rem;
		height: 2.25rem;
		border-radius: var(--radius-md);
		background: var(--color-primary-tint-2);
		color: var(--color-primary-text);
	}
	.drive-lifecycle-lists-main {
		flex: 1 1 auto;
		min-width: 0;
		display: grid;
		gap: 0.25rem;
	}
	.drive-lifecycle-lists-title-row {
		display: flex;
		flex-wrap: wrap;
		align-items: center;
		gap: 0.5rem;
	}
	.drive-lifecycle-lists-name {
		font-weight: 600;
		color: var(--color-text);
		overflow-wrap: anywhere;
	}
	.drive-lifecycle-lists-path {
		font-size: 0.75rem;
		color: var(--color-text-muted);
		overflow-wrap: anywhere;
		white-space: pre-wrap;
	}
	.drive-lifecycle-lists-chips {
		gap: 0.375rem 0.625rem;
		align-items: center;
	}
	.drive-lifecycle-lists-serial {
		font-size: 0.75rem;
		color: var(--color-text-muted);
	}
	.drive-lifecycle-lists-serial[data-warn='true'] {
		color: var(--color-on-warning-soft);
	}
	.drive-lifecycle-lists-seen {
		font-size: 0.75rem;
		color: var(--color-text-faint);
	}
	.drive-lifecycle-lists-actions {
		flex: none;
		display: flex;
		flex-wrap: wrap;
		justify-content: flex-end;
		gap: 0.5rem;
	}
	@media (max-width: 639px) {
		.drive-lifecycle-lists-head {
			flex-wrap: wrap;
		}
		.drive-lifecycle-lists-actions {
			width: 100%;
			justify-content: flex-start;
		}
	}
</style>
