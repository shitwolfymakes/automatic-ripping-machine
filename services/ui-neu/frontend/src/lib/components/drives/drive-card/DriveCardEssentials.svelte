<script lang="ts">
	import { errorMessage } from '$lib/utils/errors';
	// The drive card's essentials variant: name and 4K only, for the setup
	// walkthrough.
	import type { DriveView as Drive } from '$lib/types/api.gen';
	import { updateDrive } from '$lib/api/drives';
	import { connectionLabel, driveTitle, isRipping, mediaLabel } from '$lib/drives/drives';
	import StatusStrip from '../../shared/StatusStrip.svelte';
	import Glyph from '../../shared/Glyph.svelte';

	interface Props {
		/** The drive to show. */
		drive: Drive;
		/** Called after a name or 4K change has been saved. */
		onupdate?: () => void | Promise<void>;
	}

	let { drive, onupdate }: Props = $props();

	const conn = $derived(connectionLabel(drive));
	let essentialsName = $state<string | null>(null);
	let essentialsSaved = $state<string | null>(null);
	let essentialsError = $state<string | null>(null);
	const nameValue = $derived(essentialsName ?? drive.display_name ?? '');

	async function saveEssentialName() {
		if (essentialsName === null) return;
		const next = essentialsName.trim();
		if (next === (drive.display_name ?? '')) return;
		essentialsError = null;
		try {
			await updateDrive(drive.id, { display_name: next || null });
			essentialsSaved = 'Name saved';
			onupdate?.();
		} catch (e) {
			essentialsError = errorMessage(e, 'Saving the name failed');
		}
	}

	async function saveEssentialUhd(checked: boolean) {
		essentialsError = null;
		try {
			await updateDrive(drive.id, { uhd_capable: checked });
			essentialsSaved = '4K setting saved';
			onupdate?.();
		} catch (e) {
			essentialsError = errorMessage(e, 'Saving the 4K setting failed');
		}
	}
</script>

<div class="panel drive-card-essentials" data-testid="drive-card-essentials">
	<div class="drive-card-essentials-head">
		<span class="drive-card-essentials-icon" aria-hidden="true"><Glyph name="hard-drive" class="h-5 w-5" /></span>
		<div class="drive-card-essentials-main">
			<h3 class="drive-card-essentials-title">{driveTitle(drive)}</h3>
			<code class="mono drive-card-essentials-path"
				>{drive.device_path}{drive.by_id_name ? `  ${drive.by_id_name}` : ''}</code
			>
			<div class="cluster drive-card-essentials-chips">
				{#if conn}<span class="chip chip-sm">{conn}</span>{/if}
				<span class="chip chip-sm"><Glyph name="disc-3" class="h-3 w-3" />{mediaLabel(drive)}</span>
			</div>
		</div>
	</div>
	{#if drive.last_error}
		<StatusStrip tone="danger" title="The ripper for this drive reported a problem." message={drive.last_error} />
	{:else if drive.present === false || drive.media_status === 'detached'}
		<StatusStrip
			tone="warning"
			title="Not connected"
			detail="Reconnect the drive. It shows Ready once its ripper checks in."
		/>
	{:else if isRipping(drive)}
		<StatusStrip tone="busy" title="Ripping" detail="A disc is being ripped right now." />
	{:else if drive.notice}
		<!-- e.g. on_previously_ripped = reject ejected a disc; cleared when the
		     tray closes empty or the next disc is identified. -->
		<StatusStrip tone="warning" title="Disc ejected" detail={drive.notice} />
	{:else if drive.status === 'online'}
		<StatusStrip tone="ok" title="Ready" detail="Insert a disc any time" />
	{:else}
		<StatusStrip tone="busy" title="Starting ripper..." detail="Usually under 10 seconds" progress />
	{/if}
	<div class="field">
		<label class="field-label" for="drive-name-{drive.id}"
			>Friendly name <span class="drive-card-essentials-optional">(optional)</span></label
		>
		<input
			id="drive-name-{drive.id}"
			class="field-control"
			value={nameValue}
			placeholder={[drive.vendor, drive.model].filter(Boolean).join(' ') || 'Living room Blu-ray'}
			oninput={(e) => (essentialsName = (e.currentTarget as HTMLInputElement).value)}
			onblur={saveEssentialName}
			onkeydown={(e) => {
				if (e.key === 'Enter') saveEssentialName();
			}}
		/>
		<p class="field-help">Shown on the dashboard and in notifications.</p>
	</div>
	<label class="field field-row drive-card-essentials-uhd">
		<input
			type="checkbox"
			checked={!!drive.uhd_capable}
			onchange={(e) => saveEssentialUhd((e.currentTarget as HTMLInputElement).checked)}
		/>
		<span>
			<span class="drive-card-essentials-uhd-label">This drive can read 4K UHD discs</span>
			<span class="field-help">Only some drives can. Leave it off if you're not sure.</span>
		</span>
	</label>
	{#if essentialsError}
		<p class="field-error" role="alert">{essentialsError}</p>
	{:else if essentialsSaved}
		<p class="field-help" aria-live="polite">{essentialsSaved}</p>
	{/if}
</div>

<style>
	.drive-card-essentials {
		display: grid;
		gap: 0.875rem;
		padding: 1.25rem;
	}
	.drive-card-essentials-head {
		display: flex;
		align-items: flex-start;
		gap: 0.75rem;
	}
	.drive-card-essentials-icon {
		flex: none;
		display: grid;
		place-items: center;
		width: 2.25rem;
		height: 2.25rem;
		border-radius: var(--radius-md);
		background: var(--color-primary-tint-2);
		color: var(--color-primary-text);
	}
	.drive-card-essentials-main {
		min-width: 0;
		display: grid;
		gap: 0.25rem;
	}
	.drive-card-essentials-title {
		font-weight: 600;
		color: var(--color-text);
		overflow-wrap: anywhere;
	}
	.drive-card-essentials-path {
		font-size: 0.75rem;
		color: var(--color-text-muted);
		overflow-wrap: anywhere;
		white-space: pre-wrap;
	}
	.drive-card-essentials-chips {
		gap: 0.375rem;
	}
	.drive-card-essentials-optional {
		font-weight: 400;
		color: var(--color-text-muted);
	}
	.drive-card-essentials-uhd {
		align-items: flex-start;
		gap: 0.625rem;
	}
	.drive-card-essentials-uhd input {
		margin-top: 0.25rem;
	}
	.drive-card-essentials-uhd-label {
		display: block;
		color: var(--color-text);
	}
</style>
