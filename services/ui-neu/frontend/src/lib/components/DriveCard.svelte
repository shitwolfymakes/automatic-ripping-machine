<script lang="ts">
	import type { DriveView as Drive, SessionView } from '$lib/types/api.gen';
	import { updateDrive, unenrollDrive } from '$lib/api/drives';
	import { triggerManual } from '$lib/api/jobs';
	import { driveStatusLabel, isRipping, DETACHED_LABEL } from '$lib/utils/drives';
	import StatusBadge from './StatusBadge.svelte';
	import SkeletonCard from './SkeletonCard.svelte';
	import SlideOver from './SlideOver.svelte';
	import Glyph from './Glyph.svelte';
	import { reveal } from '$lib/transitions';

	interface Props {
		drive?: Drive;
		onupdate?: () => void | Promise<void>;
		sessions?: SessionView[];
		globalDefaults?: {
			prescan_cache_mb?: number;
			prescan_timeout?: number;
			prescan_retries?: number;
			disc_enum_timeout?: number;
		};
	}

	let { drive, onupdate, globalDefaults = {}, sessions = [] }: Props = $props();

	let editing = $state(false);
	let editName = $state('');
	let saving = $state(false);
	let togglingUhd = $state(false);
	let togglingMode = $state(false);
	let selectedSessionId = $state('');
	let triggering = $state(false);
	let manualError = $state<string | null>(null);
	let savingDefaultSession = $state(false);
	let defaultSessionError = $state<string | null>(null);
	let showSettings = $state(false);
	let speedInput = $state('');
	let savingSpeed = $state(false);
	let showAdvanced = $state(false);
	let savingPrescan = $state(false);

	// Prescan override inputs - empty string means "use global default"
	let prescanCacheInput = $state('');
	let prescanTimeoutInput = $state('');
	let prescanRetriesInput = $state('');
	let discEnumTimeoutInput = $state('');

	// Sync server values to inputs when settings panel closes
	$effect.pre(() => {
		if (!showSettings) {
			prescanCacheInput = drive?.prescan_cache_mb != null ? String(drive.prescan_cache_mb) : '';
			prescanTimeoutInput = drive?.prescan_timeout != null ? String(drive.prescan_timeout) : '';
			prescanRetriesInput = drive?.prescan_retries != null ? String(drive.prescan_retries) : '';
			discEnumTimeoutInput = drive?.disc_enum_timeout != null ? String(drive.disc_enum_timeout) : '';
		}
	});

	const PRESCAN_FIELDS = [
		{ key: 'prescan_cache_mb' as const, label: 'Pre-scan Cache', unit: 'MB', min: 1, max: 1024, input: () => prescanCacheInput, setInput: (v: string) => { prescanCacheInput = v; }, current: () => drive?.prescan_cache_mb, globalDefault: () => globalDefaults.prescan_cache_mb, tooltip: 'Community recommends 64-128 for scratched or damaged discs' },
		{ key: 'prescan_timeout' as const, label: 'Pre-scan Timeout', unit: 's', min: 30, max: 3600, input: () => prescanTimeoutInput, setInput: (v: string) => { prescanTimeoutInput = v; }, current: () => drive?.prescan_timeout, globalDefault: () => globalDefaults.prescan_timeout, tooltip: 'Community recommends 600 for slow or damaged DVD/BD media' },
		{ key: 'prescan_retries' as const, label: 'Pre-scan Retries', unit: '', min: 1, max: 10, input: () => prescanRetriesInput, setInput: (v: string) => { prescanRetriesInput = v; }, current: () => drive?.prescan_retries, globalDefault: () => globalDefaults.prescan_retries, tooltip: 'Community recommends 3-5 retries for problematic drives' },
		{ key: 'disc_enum_timeout' as const, label: 'Enum Timeout', unit: 's', min: 10, max: 600, input: () => discEnumTimeoutInput, setInput: (v: string) => { discEnumTimeoutInput = v; }, current: () => drive?.disc_enum_timeout, globalDefault: () => globalDefaults.disc_enum_timeout, tooltip: 'Community recommends 120 for drives that are slow to spin up' },
	] as const;

	async function savePrescanField(field: typeof PRESCAN_FIELDS[number]) {
		const trimmed = (field.input() ?? '').trim();
		let newVal = trimmed === '' ? null : parseInt(trimmed, 10);
		if (newVal !== null && (isNaN(newVal) || newVal < field.min || newVal > field.max)) return;
		// If the value matches the global default, store null (use global)
		if (newVal !== null && newVal === field.globalDefault()) {
			newVal = null;
			field.setInput('');
		}
		if (newVal === (field.current() ?? null)) return;

		if (!drive) return;
		savingPrescan = true;
		try {
			await updateDrive(drive.id, { [field.key]: newVal });
			onupdate?.();
		} catch {
			field.setInput(field.current() != null ? String(field.current()) : '');
		} finally {
			savingPrescan = false;
		}
	}

	$effect.pre(() => {
		const serverValue = drive?.rip_speed != null ? String(drive.rip_speed) : '';
		if (!showSettings) {
			speedInput = serverValue;
		}
	});

	async function saveSpeed() {
		if (!drive) return;
		// bind:value on a number input can hand us a number; coerce before trim.
		const trimmed = String(speedInput ?? '').trim();
		const newSpeed = trimmed === '' ? null : parseInt(trimmed, 10);

		// Skip save if value hasn't changed
		if (newSpeed === (drive.rip_speed ?? null)) return;

		// Basic validation - let the API reject out-of-range
		if (newSpeed !== null && (isNaN(newSpeed) || newSpeed < 1 || newSpeed > 99)) return;

		savingSpeed = true;
		try {
			await updateDrive(drive.id, { rip_speed: newSpeed });
			onupdate?.();
		} catch {
			// revert input on failure
			speedInput = drive.rip_speed != null ? String(drive.rip_speed) : '';
		} finally {
			savingSpeed = false;
		}
	}

	function onSpeedKeydown(e: KeyboardEvent) {
		if (e.key === 'Enter') {
			(e.target as HTMLInputElement).blur();
		}
		if (e.key === 'Escape') {
			speedInput = drive?.rip_speed != null ? String(drive.rip_speed) : '';
			showSettings = false;
		}
	}

	let statusText = $derived(drive ? driveStatusLabel(drive) : '');
	let isDetached = $derived(statusText === DETACHED_LABEL);
	let isError = $derived(drive?.status === 'error');
	let isOfflinePresent = $derived(
		!isError && !isDetached && drive?.status === 'offline' && drive?.present === true
	);

	async function startManualRip() {
		if (!drive || triggering) return;
		triggering = true;
		manualError = null;
		try {
			await triggerManual({ drive_id: drive.id, session_id: selectedSessionId || null });
			selectedSessionId = '';
			onupdate?.();
		} catch (e) {
			manualError = e instanceof Error ? e.message : 'Manual rip failed';
		} finally {
			triggering = false;
		}
	}

	async function saveDefaultSession(value: string) {
		if (!drive) return;
		savingDefaultSession = true;
		defaultSessionError = null;
		try {
			await updateDrive(drive.id, { default_session_id: value || null });
			onupdate?.();
		} catch (e) {
			defaultSessionError = e instanceof Error ? e.message : 'Failed to set default session';
		} finally {
			savingDefaultSession = false;
		}
	}

	let unenrolling = $state(false);
	let unenrollError = $state<string | null>(null);
	async function handleUnenroll() {
		if (!drive) return;
		unenrollError = null;
		const name = drive.display_name || drive.model || drive.hostname;
		if (!confirm(`Unenroll ${name}? Its ripper container is stopped and removed. If the drive is still connected it reappears under Detected on the next scan.`)) return;
		unenrolling = true;
		try {
			await unenrollDrive(drive.id);
			await onupdate?.();
		} catch (e) {
			unenrollError = e instanceof Error ? e.message : 'Unenroll failed';
		} finally {
			unenrolling = false;
		}
	}

	function startEdit() {
		editName = drive?.display_name || '';
		editing = true;
	}

	function cancelEdit() {
		editing = false;
	}

	async function saveEdit() {
		if (!drive) return;
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

	async function toggleUhd() {
		if (!drive) return;
		togglingUhd = true;
		try {
			await updateDrive(drive.id, { uhd_capable: !drive.uhd_capable });
			onupdate?.();
		} catch {
			// ignore
		} finally {
			togglingUhd = false;
		}
	}

	function onKeydown(e: KeyboardEvent) {
		if (e.key === 'Enter') saveEdit();
		if (e.key === 'Escape') cancelEdit();
	}

	async function toggleMode() {
		if (!drive) return;
		togglingMode = true;
		const newMode = drive.drive_mode === 'manual' ? 'auto' : 'manual';
		try {
			await updateDrive(drive.id, { drive_mode: newMode });
			onupdate?.();
		} catch {
			// ignore
		} finally {
			togglingMode = false;
		}
	}

</script>

{#if !drive}
	<SkeletonCard />
{:else}
<!-- Plain `card`, deliberately NOT `card card-status`: the original card shell
     (git 441d35d2, `rounded-lg border border-primary/20 bg-surface p-2.5
     shadow-xs`) carried no status-driven styling at all. Drive status only ever
     coloured the inline label/badge in the header, never the card itself, so
     `card-status`'s 4px left accent stripe would be a new visual element the
     baseline has no counterpart for. `isDetached` is the one shell-level state
     the original had (`opacity-60`), kept here as `data-detached`. -->
<div class="card drive-card" data-detached={isDetached}>
	<!-- Header: name + rename + status -->
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
				<span class="flex-shrink-0 badge badge-warning badge-sm drive-card-status-pill" data-testid="drive-status-label">{statusText}</span>
			{:else if !editing}
				<button
					onclick={startEdit}
					class="btn btn-link btn-sm flex-shrink-0"
				>Rename</button>
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
			<button
				onclick={saveEdit}
				disabled={saving}
				class="btn btn-primary btn-sm"
			>Save</button>
			<button
				onclick={cancelEdit}
				disabled={saving}
				class="btn btn-ghost btn-sm"
			>Cancel</button>
		</div>
	{/if}

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
		{#if drive.rip_speed != null || [drive.prescan_cache_mb, drive.prescan_timeout, drive.prescan_retries, drive.disc_enum_timeout].some(v => v != null)}
			<div class="flex flex-wrap items-center gap-1 pt-0.5">
				{#if drive.rip_speed != null}
					<span in:reveal class="drive-card-chip drive-card-chip-speed">
						<Glyph name="gear" class="h-2.5 w-2.5" />
						{drive.rip_speed}x speed
					</span>
				{/if}
				{#if [drive.prescan_cache_mb, drive.prescan_timeout, drive.prescan_retries, drive.disc_enum_timeout].some(v => v != null)}
					{@const prescanOverrideCount = [drive.prescan_cache_mb, drive.prescan_timeout, drive.prescan_retries, drive.disc_enum_timeout].filter(v => v != null).length}
					<span in:reveal class="drive-card-chip drive-card-chip-warning">
						{prescanOverrideCount} custom
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
				disabled={togglingUhd}
				onchange={toggleUhd}
				class="drive-card-uhd-checkbox"
			/>
			4K
			<Glyph name="info" class="h-3 w-3 drive-card-uhd-info" />
		</label>
	</div>

	<!-- Consolidated action bar -->
	<div class="flex items-center gap-1 drive-card-action-bar">
		<button
			onclick={toggleMode}
			disabled={togglingMode}
			class="drive-card-mode-btn"
			data-manual={drive.drive_mode === 'manual'}
			title="Toggle between auto and manual rip mode"
		>
			{drive.drive_mode === 'manual' ? 'Manual' : 'Auto'}
		</button>

		<select
			bind:value={selectedSessionId}
			data-testid="drive-session-select"
			disabled={triggering}
			title="Optional session - auto-applies when the rip completes"
			class="min-w-0 flex-1 drive-card-session-select"
		>
			<option value="">- none -</option>
			{#each sessions as s (s.id)}
				<option value={s.id}>{s.name}{s.is_builtin ? ' (built-in)' : ''}</option>
			{/each}
		</select>
		<button
			onclick={startManualRip}
			disabled={triggering}
			data-testid="drive-start-rip"
			class="flex items-center justify-center gap-1 btn btn-primary btn-sm drive-card-start-btn"
			title="Start a manual rip on this drive"
		>
			{triggering ? 'Starting...' : 'Start rip'}
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
			onclick={handleUnenroll}
			disabled={unenrolling || isRipping(drive)}
			title={isRipping(drive) ? 'Cannot unenroll while ripping' : 'Stop and remove this drive\'s ripper'}
			class="btn btn-danger btn-sm drive-card-unenroll-btn"
		>{unenrolling ? 'Unenrolling...' : 'Unenroll'}</button>
	</div>

	{#if manualError}
		<p class="field-error mt-1 drive-card-error" data-testid="drive-manual-error">{manualError}</p>
	{/if}

	{#if unenrollError}
		<p class="field-error mt-1 drive-card-error" data-testid="drive-unenroll-error">{unenrollError}</p>
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
	<SlideOver bind:open={showSettings} title="{drive.display_name || drive.device_path || 'Drive'} settings" width="max-w-md">
		<div class="flex flex-col gap-5 drive-card-settings-body">
			<div class="field">
				<label for="default-session-{drive.id}" class="field-label">Default session</label>
				<select
					id="default-session-{drive.id}"
					data-testid="drive-default-session"
					value={drive.default_session_id ?? ''}
					onchange={(e) => saveDefaultSession((e.currentTarget as HTMLSelectElement).value)}
					disabled={savingDefaultSession}
				>
					<option value="">- none -</option>
					{#each sessions as s (s.id)}
						<option value={s.id}>{s.name}{s.is_builtin ? ' (built-in)' : ''}</option>
					{/each}
				</select>
				<p class="field-help">Auto-applied to auto-mode rips on this drive.</p>
				{#if defaultSessionError}
					<p class="field-error" data-testid="drive-default-session-error">{defaultSessionError}</p>
				{/if}
			</div>

			<div class="field">
				<div class="flex items-center justify-between gap-2">
					<label for="rip-speed-{drive.id}" class="field-label">Rip Speed</label>
					<input
						id="rip-speed-{drive.id}"
						type="number"
						min="1"
						max="99"
						bind:value={speedInput}
						onblur={saveSpeed}
						onkeydown={onSpeedKeydown}
						disabled={savingSpeed}
						class="drive-card-number-input"
					/>
				</div>
				<p class="field-help">Empty = max speed. Lower values help with read errors on problematic discs.</p>
			</div>

			<div class="stack drive-card-prescan-section">
				<div class="eyebrow">Pre-scan tuning</div>
				{#each PRESCAN_FIELDS as field}
					<div class="field">
						<div class="flex items-center justify-between gap-2">
							<label for="prescan-{field.key}-{drive.id}" class="field-label">
								{field.label}{#if field.unit}&nbsp;<span class="drive-card-unit">({field.unit})</span>{/if}
							</label>
							<input
								id="prescan-{field.key}-{drive.id}"
								type="number"
								min={field.min}
								max={field.max}
								placeholder={field.globalDefault() != null ? String(field.globalDefault()) : ''}
								value={field.input()}
								oninput={(e) => field.setInput((e.target as HTMLInputElement).value)}
								onblur={() => savePrescanField(field)}
								onkeydown={(e) => {
									if (e.key === 'Enter') (e.target as HTMLInputElement).blur();
									if (e.key === 'Escape') {
										field.setInput(field.current() != null ? String(field.current()) : '');
										showSettings = false;
									}
								}}
								disabled={savingPrescan}
								class="drive-card-number-input"
							/>
						</div>
						<p class="field-help">{field.tooltip}</p>
					</div>
				{/each}
			</div>
		</div>
	</SlideOver>
</div>
{/if}

<style>
	/* DriveCard packs a lot of state into a small footprint (11px title,
	   9-10px chips, tight action bar) - a fair bit denser than the shared
	   card/badge/btn metrics, so most of its internals are scoped rather
	   than block classes. */
	.drive-card { padding: 0.625rem; }
	.drive-card[data-detached="true"] { opacity: 0.6; }
	.drive-card-title { font-weight: 600; font-size: 0.875rem; color: var(--color-text); }
	/* text-xs text-gray-400 - a plain inline span in a flex row, not
	   panel-hint's block-level note (whose own margin-top would misalign
	   it against its row siblings) or its muted (not faint) color. */
	.drive-card-idle { font-size: 0.75rem; line-height: 1rem; color: var(--color-text-faint); }
	.drive-card-status-error { font-size: 0.625rem; font-weight: 500; color: var(--color-danger); }
	/* badge-warning is a solid fill; this pill was always a soft amber tint
	   (bg-amber-500/20 text-amber-700), closer to alert-warning's tone. */
	.drive-card-status-pill { background: var(--color-warning-soft); color: var(--color-on-warning-soft); }
	.drive-card-edit-input { font-size: 0.875rem; font-weight: 600; }

	/* the original was space-y-0.5 (0.125rem) - finer than stack-sm's
	   0.5rem, so this needs its own flex column and gap. */
	.drive-card-info { display: flex; flex-direction: column; gap: 0.125rem; font-size: 0.6875rem; line-height: 1.25; }
	.drive-card-info-label { color: var(--color-text-muted); }
	.drive-card-info-value { color: var(--color-text-secondary); }
	.drive-card-info-mono { font-size: 0.625rem; }

	.drive-card-chip { display: inline-flex; align-items: center; gap: 0.125rem; border-radius: var(--radius-sm); padding: 0.125rem 0.375rem; font-size: 0.5625rem; font-weight: 500; }
	.drive-card-chip-speed { background: color-mix(in srgb, var(--color-info) 15%, transparent); color: var(--color-info); }
	.drive-card-chip-warning { background: var(--color-warning-soft); color: var(--color-on-warning-soft); }
	.drive-card-chip-primary { background: var(--color-primary-tint-3); color: var(--color-primary-text); font-size: 0.625rem; }
	.drive-card-uhd { cursor: pointer; }
	.drive-card-uhd-checkbox { width: 0.75rem; height: 0.75rem; border-radius: var(--radius-sm); accent-color: var(--color-warning); }
	:global(.drive-card-uhd-info) { color: var(--color-text-faint); } /* :global: forwarded onto Glyph's internal <svg>, outside this component's own template */

	.drive-card-action-bar { border: 1px solid var(--color-border); border-radius: var(--radius-lg); background: color-mix(in srgb, var(--color-surface-raised) 2.5%, transparent); padding: 0.25rem; }
	.drive-card-mode-btn { border-radius: var(--radius-md); padding: 0.375rem 0.625rem; font-size: 0.6875rem; font-weight: 600; text-transform: uppercase; letter-spacing: 0.05em; background: var(--color-primary-tint-2); color: var(--color-primary-text); cursor: pointer; transition: background-color var(--motion-fast) var(--ease); }
	.drive-card-mode-btn:hover { background: var(--color-primary-tint-3); }
	.drive-card-mode-btn:disabled { opacity: 0.5; cursor: not-allowed; }
	.drive-card-mode-btn[data-manual="true"] { background: var(--color-warning-soft); color: var(--color-on-warning-soft); }
	.drive-card-mode-btn[data-manual="true"]:hover { background: color-mix(in srgb, var(--color-warning) 30%, transparent); }
	.drive-card-session-select { border-radius: var(--radius-md); border: 1px solid var(--color-border); background: var(--color-primary-tint-1); padding: 0.375rem 0.5rem; font-size: 0.75rem; color: var(--color-text); }
	.drive-card-session-select:disabled { opacity: 0.5; }
	.drive-card-start-btn { min-height: auto; padding: 0.375rem 0.625rem; }
	.drive-card-action-divider { width: 1px; height: 1.5rem; background: var(--color-border); }
	.drive-card-gear-btn[aria-pressed="true"] { background: var(--color-primary-tint-3); color: var(--color-primary-text); }
	.drive-card-unenroll-btn { min-height: auto; padding: 0.375rem 0.5rem; }

	.drive-card-error { font-size: 0.6875rem; }
	.drive-card-current-rip { border-top: 1px solid var(--color-border); padding-top: 0.375rem; }
	.drive-card-current-rip-label { font-size: 0.625rem; font-weight: 600; color: var(--color-text-muted); }
	.drive-card-current-rip-link { font-size: 0.6875rem; color: var(--color-primary-text); }
	.drive-card-current-rip-link:hover { text-decoration: underline; }

	.drive-card-settings-body { font-size: 0.875rem; }
	.drive-card-number-input { width: 6rem; text-align: center; }
	/* the original was space-y-3 (0.75rem) - between stack-sm's 0.5rem and
	   stack's own 1rem, so neither modifier matches exactly. */
	.drive-card-prescan-section { gap: 0.75rem; border-top: 1px solid var(--color-border-strong); padding-top: 1rem; }
	.drive-card-unit { font-size: 0.75rem; color: var(--color-text-faint); }
</style>
