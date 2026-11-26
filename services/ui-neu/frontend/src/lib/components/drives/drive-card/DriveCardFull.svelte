<script lang="ts">
	import type { DriveView as Drive, SessionView, TranscodePresetView } from '$lib/types/api.gen';
	import { transcoderEnabled } from '$lib/stores/config';
	import { sessionOptionLabel } from '$lib/sessions/routes';
	import { DriveCardActions } from '$lib/stores/drive-card-actions.svelte';
	import { defaultSessionChoices, manualRipSessionChoices } from '$lib/sessions/sessions';
	import { hasLiveJob, isDriveDetached, prescanOverrideCount, startRipBlockedReason } from '$lib/drives/drives';
	import type { PrescanKey } from '$lib/drives/settings';
	import DriveSettingsPanel from './DriveSettingsPanel.svelte';
	import DriveCardHeader from './DriveCardHeader.svelte';
	import Glyph from '../../shared/Glyph.svelte';
	import ConfirmDialog from '../../shared/ConfirmDialog.svelte';
	import { reveal } from '$lib/ui/transitions';

	interface Props {
		/** The drive this card shows. */
		drive: Drive;
		/** Called after a change that the drive list should refresh for. */
		onupdate?: () => void | Promise<void>;
		/** The sessions the manual-rip and default-session pickers offer. */
		sessions: SessionView[];
		/**
		 * Transcode presets, used only to tell passthrough sessions apart
		 * from encode ones on a ripper-only deployment (see pickerSessions).
		 */
		transcodePresets: TranscodePresetView[];
		/** The global prescan defaults the settings panel shows beside each override. */
		globalDefaults: Partial<Record<PrescanKey, number>>;
		/** The global auto-rip default a drive with no mode of its own follows. */
		globalAutoRip: boolean;
	}

	// DriveCard applies the defaults, so every prop but onupdate is required here.
	let { drive, onupdate, globalDefaults, sessions, transcodePresets, globalAutoRip }: Props = $props();

	const isDetached = $derived(isDriveDetached(drive));
	const startRipBlocked = $derived(startRipBlockedReason(drive));
	const prescanOverrides = $derived(prescanOverrideCount(drive));

	const pickerSessions = $derived(manualRipSessionChoices(sessions, transcodePresets, $transcoderEnabled));
	const defaultPickerSessions = $derived(
		defaultSessionChoices(sessions, transcodePresets, $transcoderEnabled, drive.default_session_id)
	);

	const actions = new DriveCardActions(() => onupdate?.());
	let showSettings = $state(false);

	const unenrollName = $derived(drive.display_name || drive.model || drive.hostname);
</script>

<!-- Plain `card`, deliberately NOT `card card-status`: the drive card carries no status-driven
     styling. Drive status only colours the inline label/badge in the header, never the card itself,
     so `card-status`'s 4px left accent stripe would be a visual element with no counterpart.
     `isDetached` is the one shell-level state (dimmed with `opacity-60`), set here as
     `data-detached`. -->
<div class="card drive-card" data-detached={isDetached}>
	<!-- Header: name + rename + status -->
	<DriveCardHeader {drive} {onupdate} />

	<!-- Drive info: labeled name:value rows -->
	<div class="mb-1.5 drive-card-info">
		{#if drive.device_path}
			<div class="flex gap-1.5">
				<span class="drive-card-info-label">Device:</span>
				<span class="mono drive-card-info-value drive-card-info-mono">{drive.device_path}</span>
			</div>
		{/if}
		{#if drive.hostname}
			<div class="flex gap-1.5">
				<span class="drive-card-info-label">Host:</span>
				<span class="drive-card-info-value">{drive.hostname}</span>
			</div>
		{/if}
		{#if drive.rip_speed != null || prescanOverrides > 0}
			<div class="flex flex-wrap items-center gap-1 pt-0.5">
				{#if drive.rip_speed != null}
					<span in:reveal class="drive-card-chip drive-card-chip-speed">
						<Glyph name="gear" class="h-2.5 w-2.5" />
						{drive.rip_speed}x speed
					</span>
				{/if}
				{#if prescanOverrides > 0}
					<span in:reveal class="drive-card-chip drive-card-chip-warning">
						{prescanOverrides} custom
					</span>
				{/if}
			</div>
		{/if}
	</div>

	<!-- Media status + 4K -->
	<div class="mb-2 flex flex-wrap items-center gap-1">
		{#if drive.media_status}
			<span class="drive-card-chip drive-card-chip-primary">
				{drive.media_status.replace('_', ' ')}
			</span>
		{/if}
		<label
			class="drive-card-chip drive-card-chip-warning drive-card-uhd"
			title="Display only - UHD disc detection and transcoding presets are applied automatically regardless of this setting."
		>
			<input
				type="checkbox"
				checked={drive.uhd_capable ?? false}
				disabled={actions.togglingUhd}
				onchange={() => actions.toggleUhd(drive)}
				class="drive-card-uhd-checkbox"
			/>
			4K
			<Glyph name="info" class="h-3 w-3 drive-card-uhd-info" />
		</label>
	</div>

	<!-- Consolidated action bar -->
	<div class="flex items-center gap-1 drive-card-action-bar">
		<select
			class="drive-card-mode-btn"
			aria-label="Rip mode"
			title="Rip on insert (Auto), wait for Start (Manual), or follow the global default"
			disabled={actions.togglingMode}
			data-manual={drive.drive_mode === 'manual' || (drive.drive_mode == null && !globalAutoRip)}
			value={drive.drive_mode ?? ''}
			onchange={(e) => actions.setMode(drive.id, (e.currentTarget as HTMLSelectElement).value)}
		>
			<option value="">Default ({globalAutoRip ? 'Auto' : 'Manual'})</option>
			<option value="auto">Auto</option>
			<option value="manual">Manual</option>
		</select>

		<select
			bind:value={actions.selectedSessionId}
			data-testid="drive-session-select"
			disabled={actions.triggering}
			title="Optional session - auto-applies when the rip completes"
			class="min-w-0 flex-1 drive-card-session-select"
		>
			<option value="">- none -</option>
			{#each pickerSessions as s (s.id)}
				<option value={s.id}>{sessionOptionLabel(s)}</option>
			{/each}
		</select>
		<button
			onclick={() => actions.startManualRip(drive.id)}
			disabled={actions.triggering || startRipBlocked !== null}
			data-testid="drive-start-rip"
			class="flex items-center justify-center gap-1 btn btn-primary btn-sm drive-card-start-btn"
			title={startRipBlocked ?? 'Start a manual rip on this drive'}
		>
			{actions.triggering ? 'Starting...' : 'Start rip'}
		</button>

		<div class="drive-card-action-divider"></div>

		<button
			onclick={() => (showSettings = true)}
			class="btn btn-icon drive-card-gear-btn"
			aria-pressed={showSettings}
			title="Drive settings"
		>
			<Glyph name="gear" class="h-3.5 w-3.5" />
		</button>

		<button
			data-testid="drive-unenroll"
			onclick={actions.requestUnenroll}
			disabled={actions.unenrolling || hasLiveJob(drive)}
			title={hasLiveJob(drive)
				? 'Cannot unenroll while the drive has a job in progress'
				: "Stop and remove this drive's ripper"}
			class="btn btn-danger btn-sm drive-card-unenroll-btn"
			>{actions.unenrolling ? 'Unenrolling...' : 'Unenroll'}</button
		>
	</div>

	{#if actions.manualError}
		<p class="field-error mt-1 drive-card-error" data-testid="drive-manual-error">{actions.manualError}</p>
	{/if}

	{#if actions.unenrollError}
		<p class="field-error mt-1 drive-card-error" data-testid="drive-unenroll-error">{actions.unenrollError}</p>
	{/if}

	<!-- Current rip -->
	{#if drive.current_job}
		<div class="mt-2 drive-card-current-rip">
			<span class="drive-card-current-rip-label">Current Rip</span>
			<a href="/jobs/{drive.current_job.id}" class="block truncate drive-card-current-rip-link">
				{drive.current_job.title || 'Active Job'}
			</a>
		</div>
	{/if}

	<!-- Drive settings slide-over -->
	<DriveSettingsPanel {drive} bind:open={showSettings} sessions={defaultPickerSessions} {globalDefaults} {onupdate} />
</div>

<ConfirmDialog
	open={actions.confirmUnenrollOpen}
	title="Unenroll {unenrollName}?"
	message="Its ripper container is stopped and removed. If the drive is still connected it reappears under Detected on the next scan."
	confirmLabel="Unenroll"
	variant="danger"
	onconfirm={() => actions.confirmUnenroll(drive.id)}
	oncancel={actions.cancelUnenroll}
/>

<style>
	/* DriveCard packs a lot of state into a small footprint (11px title,
	   9-10px chips, tight action bar) - a fair bit denser than the shared
	   card/badge/btn metrics, so most of its internals are scoped rather
	   than block classes. */
	.drive-card {
		padding: 0.625rem;
	}
	.drive-card[data-detached='true'] {
		opacity: 0.6;
	}

	/* the gap is 0.125rem - finer than stack-sm's 0.5rem, so this needs its own flex column and gap. */
	.drive-card-info {
		display: flex;
		flex-direction: column;
		gap: 0.125rem;
		font-size: 0.6875rem;
		line-height: 1.25;
	}
	.drive-card-info-label {
		color: var(--color-text-muted);
	}
	.drive-card-info-value {
		color: var(--color-text-secondary);
	}
	.drive-card-info-mono {
		font-size: 0.625rem;
	}

	.drive-card-chip {
		display: inline-flex;
		align-items: center;
		gap: 0.125rem;
		border-radius: var(--radius-sm);
		padding: 0.125rem 0.375rem;
		font-size: 0.5625rem;
		font-weight: 500;
	}
	.drive-card-chip-speed {
		background: color-mix(in srgb, var(--color-info) 15%, transparent);
		color: var(--color-info);
	}
	.drive-card-chip-warning {
		background: var(--color-warning-soft);
		color: var(--color-on-warning-soft);
	}
	.drive-card-chip-primary {
		background: var(--color-primary-tint-3);
		color: var(--color-primary-text);
		font-size: 0.625rem;
	}
	.drive-card-uhd {
		cursor: pointer;
	}
	.drive-card-uhd-checkbox {
		width: 0.75rem;
		height: 0.75rem;
		border-radius: var(--radius-sm);
		accent-color: var(--color-warning);
	}
	/* :global: forwarded onto Glyph's internal <svg>, outside this component's own template */
	:global(.drive-card-uhd-info) {
		color: var(--color-text-faint);
	}

	.drive-card-action-bar {
		border: 1px solid var(--color-border);
		border-radius: var(--radius-lg);
		background: color-mix(in srgb, var(--color-surface-raised) 2.5%, transparent);
		padding: 0.25rem;
	}
	.drive-card-mode-btn {
		border-radius: var(--radius-md);
		padding: 0.375rem 0.625rem;
		font-size: 0.6875rem;
		font-weight: 600;
		text-transform: uppercase;
		letter-spacing: 0.05em;
		background: var(--color-primary-tint-2);
		color: var(--color-primary-text);
		cursor: pointer;
		transition: background-color var(--motion-fast) var(--ease);
	}
	.drive-card-mode-btn:hover {
		background: var(--color-primary-tint-3);
	}
	.drive-card-mode-btn:disabled {
		opacity: 0.5;
		cursor: not-allowed;
	}
	.drive-card-mode-btn[data-manual='true'] {
		background: var(--color-warning-soft);
		color: var(--color-on-warning-soft);
	}
	.drive-card-mode-btn[data-manual='true']:hover {
		background: color-mix(in srgb, var(--color-warning) 30%, transparent);
	}
	.drive-card-session-select {
		border-radius: var(--radius-md);
		border: 1px solid var(--color-border);
		background: var(--color-primary-tint-1);
		padding: 0.375rem 0.5rem;
		font-size: 0.75rem;
		color: var(--color-text);
	}
	.drive-card-session-select:disabled {
		opacity: 0.5;
	}
	.drive-card-start-btn {
		min-height: auto;
		padding: 0.375rem 0.625rem;
	}
	.drive-card-action-divider {
		width: 1px;
		height: 1.5rem;
		background: var(--color-border);
	}
	.drive-card-gear-btn[aria-pressed='true'] {
		background: var(--color-primary-tint-3);
		color: var(--color-primary-text);
	}
	.drive-card-unenroll-btn {
		min-height: auto;
		padding: 0.375rem 0.5rem;
	}

	.drive-card-error {
		font-size: 0.6875rem;
	}
	.drive-card-current-rip {
		border-top: 1px solid var(--color-border);
		padding-top: 0.375rem;
	}
	.drive-card-current-rip-label {
		font-size: 0.625rem;
		font-weight: 600;
		color: var(--color-text-muted);
	}
	.drive-card-current-rip-link {
		font-size: 0.6875rem;
		color: var(--color-primary-text);
	}
	.drive-card-current-rip-link:hover {
		text-decoration: underline;
	}
</style>
