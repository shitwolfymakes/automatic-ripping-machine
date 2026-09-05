<script lang="ts">
	import type { DriveView as Drive, SessionView } from '$lib/types/api.gen';
	import { updateDrive, unenrollDrive } from '$lib/api/drives';
	import { triggerManual } from '$lib/api/jobs';
	import { driveStatusLabel, isRipping, DETACHED_LABEL } from '$lib/utils/drives';
	import StatusBadge from './StatusBadge.svelte';
	import SkeletonCard from './SkeletonCard.svelte';
	import SlideOver from './SlideOver.svelte';

	interface Props {
		drive?: Drive;
		onupdate?: () => void;
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
	async function handleUnenroll() {
		if (!drive) return;
		const name = drive.display_name || drive.model || drive.hostname;
		if (!confirm(`Unenroll ${name}? Its ripper container is stopped and removed; the drive will reappear under Detected on the next rescan.`)) return;
		unenrolling = true;
		try {
			await unenrollDrive(drive.id);
			onupdate?.();
		} catch {
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
<div class="rounded-lg border border-primary/20 bg-surface p-2.5 shadow-xs dark:border-primary/20 dark:bg-surface-dark {isDetached ? 'opacity-60' : ''}">
	<!-- Header: name + rename + status -->
	<div class="mb-1 flex items-center justify-between">
		<div class="flex min-w-0 items-center gap-1.5">
			<h3 class="truncate font-semibold text-gray-900 dark:text-white">
				{drive.display_name || drive.device_path || `Drive ${drive.id}`}
			</h3>
			{#if isDetached}
				<span class="flex-shrink-0 rounded-full bg-amber-500/20 px-2 py-0.5 text-[10px] font-medium text-amber-700 dark:text-amber-400">{statusText}</span>
			{:else if isError}
				<span class="flex-shrink-0 text-[10px] font-medium text-red-600 dark:text-red-400" title={statusText}>{statusText}</span>
			{:else if !editing}
				<button
					onclick={startEdit}
					class="flex-shrink-0 rounded border border-primary/15 px-1.5 py-0 text-[10px] text-gray-500 hover:bg-primary/10 dark:border-primary/20 dark:text-gray-400 dark:hover:bg-primary/15"
				>Rename</button>
			{/if}
		</div>
		{#if drive.current_job}
			<StatusBadge status={drive.current_job.status} />
		{:else}
			<span class="flex-shrink-0 text-xs text-gray-400">Idle</span>
		{/if}
	</div>

	<!-- Name editing -->
	{#if editing}
		<div class="mb-2 flex items-center gap-2">
			<input
				type="text"
				bind:value={editName}
				onkeydown={onKeydown}
				class="rounded-sm border border-primary/25 bg-primary/5 px-2 py-1 text-sm font-semibold text-gray-900 dark:border-primary/30 dark:bg-primary/10 dark:text-white"
				disabled={saving}
			/>
			<button
				onclick={saveEdit}
				disabled={saving}
				class="rounded-sm bg-primary px-2 py-1 text-xs text-on-primary hover:bg-primary-hover disabled:opacity-50"
			>Save</button>
			<button
				onclick={cancelEdit}
				disabled={saving}
				class="rounded-sm px-2 py-1 text-xs text-gray-500 hover:text-gray-700 dark:text-gray-400 dark:hover:text-gray-200"
			>Cancel</button>
		</div>
	{/if}

	<!-- Drive info -->
	<div class="mb-1.5 text-[11px] leading-relaxed text-gray-500 dark:text-gray-400">
		{#if drive.device_path}
			<span class="font-mono text-[10px]">{drive.device_path}</span>
		{/if}
		{#if drive.hostname}
			{#if drive.device_path} | {/if}<span>{drive.hostname}</span>
		{/if}
		<br/>
		{#if drive.rip_speed != null}
			<span class="ml-1 inline-flex items-center gap-0.5 rounded-sm bg-blue-500/15 px-1.5 py-0.5 text-[9px] font-medium text-blue-400">
				<svg class="h-2.5 w-2.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.066 2.573c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.573 1.066c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.066-2.573c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z" /><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" /></svg>
				{drive.rip_speed}x speed
			</span>
		{/if}
		{#if [drive.prescan_cache_mb, drive.prescan_timeout, drive.prescan_retries, drive.disc_enum_timeout].some(v => v != null)}
			{@const prescanOverrideCount = [drive.prescan_cache_mb, drive.prescan_timeout, drive.prescan_retries, drive.disc_enum_timeout].filter(v => v != null).length}
			<span class="ml-1 inline-flex items-center gap-0.5 rounded-sm bg-amber-500/15 px-1.5 py-0.5 text-[9px] font-medium text-amber-600 dark:text-amber-400">
				{prescanOverrideCount} custom
			</span>
		{/if}
	</div>

	<!-- Media status + 4K -->
	<div class="mb-2 flex flex-wrap items-center gap-1">
		{#if drive.media_status}
			<span class="inline-flex items-center gap-1 rounded-sm bg-primary/15 px-1.5 py-0.5 text-[10px] text-primary-text dark:text-primary-text-dark">
				{drive.media_status.replace('_', ' ')}
			</span>
		{/if}
		<label
			class="inline-flex items-center gap-1 rounded-sm bg-amber-500/15 px-1.5 py-0.5 text-[10px] text-amber-700 dark:text-amber-400"
			title="Display only - UHD disc detection and transcoding presets are applied automatically regardless of this setting."
		>
			<input
				type="checkbox"
				checked={drive.uhd_capable ?? false}
				disabled={togglingUhd}
				onchange={toggleUhd}
				class="h-3 w-3 rounded-sm border-gray-300 text-amber-600 focus:ring-amber-500 dark:border-gray-600 dark:bg-gray-700"
			/>
			4K
			<svg class="h-3 w-3 text-gray-400 dark:text-gray-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
				<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
			</svg>
		</label>
	</div>

	<!-- Consolidated action bar -->
	<div class="flex items-center gap-1 rounded-lg border border-primary/10 bg-white/[0.025] p-1 dark:border-primary/10">
		<button
			onclick={toggleMode}
			disabled={togglingMode}
			class="rounded-md px-2.5 py-1.5 text-[11px] font-semibold uppercase tracking-wider transition-colors
				{drive.drive_mode === 'manual'
					? 'bg-amber-500/20 text-amber-700 hover:bg-amber-500/30 dark:text-amber-400'
					: 'bg-primary/10 text-primary-text hover:bg-primary/20 dark:text-primary-text-dark'}
				disabled:opacity-50"
			title="Toggle between auto and manual rip mode"
		>
			{drive.drive_mode === 'manual' ? 'Manual' : 'Auto'}
		</button>

		<select
			bind:value={selectedSessionId}
			data-testid="drive-session-select"
			disabled={triggering}
			title="Optional session - auto-applies when the rip completes"
			class="min-w-0 flex-1 rounded-md border border-primary/15 bg-primary/5 px-2 py-1.5 text-xs text-gray-900 dark:border-primary/20 dark:bg-primary/10 dark:text-white disabled:opacity-50"
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
			class="flex items-center justify-center gap-1 rounded-md bg-primary px-2.5 py-1.5 text-xs font-semibold text-on-primary transition-colors hover:bg-primary-hover disabled:opacity-50"
			title="Start a manual rip on this drive"
		>
			{triggering ? 'Starting...' : 'Start rip'}
		</button>

		<div class="h-6 w-px bg-primary/10 dark:bg-primary/15"></div>

		<button
			onclick={() => (showSettings = true)}
			class="flex items-center justify-center rounded-md px-1.5 py-1.5 text-xs transition-colors
				{showSettings
					? 'bg-primary/20 text-primary-text dark:text-white'
					: 'bg-primary/10 text-gray-500 hover:bg-primary/20 hover:text-primary-text dark:text-gray-400 dark:hover:text-primary-text-dark'}"
			title="Drive settings"
		>
			<svg class="h-3.5 w-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
				<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.066 2.573c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.573 1.066c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.066-2.573c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z" />
				<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
			</svg>
		</button>

		<button
			data-testid="drive-unenroll"
			onclick={handleUnenroll}
			disabled={unenrolling || isRipping(drive)}
			title={isRipping(drive) ? 'Cannot unenroll while ripping' : 'Stop and remove this drive\'s ripper'}
			class="rounded-md bg-red-500/15 px-2 py-1.5 text-xs font-medium text-red-700 transition-colors hover:bg-red-500/25 disabled:opacity-50 dark:text-red-400 dark:hover:bg-red-500/30"
		>{unenrolling ? 'Unenrolling...' : 'Unenroll'}</button>
	</div>

	{#if manualError}
		<p class="mt-1 text-[11px] text-red-600 dark:text-red-400" data-testid="drive-manual-error">{manualError}</p>
	{/if}

	<!-- Current rip -->
	{#if drive.current_job}
		<div class="mt-2 border-t border-primary/10 pt-1.5 dark:border-primary/15">
			<span class="text-[10px] font-semibold text-gray-500 dark:text-gray-400">Current Rip</span>
			<a href="/jobs/{drive.current_job.id}" class="block truncate text-[11px] text-primary-text hover:underline dark:text-primary-text-dark">
				{drive.current_job.title || 'Active Job'}
			</a>
		</div>
	{/if}

	<!-- Drive settings slide-over -->
	<SlideOver bind:open={showSettings} title="{drive.display_name || drive.device_path || 'Drive'} settings" width="max-w-md">
		<div class="flex flex-col gap-5 text-sm">
			<div>
				<label for="default-session-{drive.id}" class="mb-1 block font-medium text-gray-700 dark:text-gray-300">Default session</label>
				<select
					id="default-session-{drive.id}"
					data-testid="drive-default-session"
					value={drive.default_session_id ?? ''}
					onchange={(e) => saveDefaultSession((e.currentTarget as HTMLSelectElement).value)}
					disabled={savingDefaultSession}
					class="w-full rounded-md border border-primary/25 bg-primary/5 px-3 py-2 text-gray-900 dark:border-primary/30 dark:bg-primary/10 dark:text-white disabled:opacity-50"
				>
					<option value="">- none -</option>
					{#each sessions as s (s.id)}
						<option value={s.id}>{s.name}{s.is_builtin ? ' (built-in)' : ''}</option>
					{/each}
				</select>
				<p class="mt-1 text-xs leading-snug text-gray-400 dark:text-gray-500">Auto-applied to auto-mode rips on this drive.</p>
				{#if defaultSessionError}
					<p class="mt-1 text-xs text-red-600 dark:text-red-400" data-testid="drive-default-session-error">{defaultSessionError}</p>
				{/if}
			</div>

			<div>
				<div class="flex items-center justify-between gap-2">
					<label for="rip-speed-{drive.id}" class="font-medium text-gray-700 dark:text-gray-300">Rip Speed</label>
					<input
						id="rip-speed-{drive.id}"
						type="number"
						min="1"
						max="99"
						bind:value={speedInput}
						onblur={saveSpeed}
						onkeydown={onSpeedKeydown}
						disabled={savingSpeed}
						class="w-24 rounded-md border border-primary/25 bg-primary/5 px-3 py-2 text-center text-gray-900 dark:border-primary/30 dark:bg-primary/10 dark:text-white disabled:opacity-50"
					/>
				</div>
				<p class="mt-1 text-xs leading-snug text-gray-400 dark:text-gray-500">Empty = max speed. Lower values help with read errors on problematic discs.</p>
			</div>

			<div class="space-y-3 border-t border-primary/15 pt-4">
				<div class="text-xs font-semibold uppercase tracking-wider text-gray-500 dark:text-gray-400">Pre-scan tuning</div>
				{#each PRESCAN_FIELDS as field}
					<div>
						<div class="flex items-center justify-between gap-2">
							<label for="prescan-{field.key}-{drive.id}" class="text-gray-700 dark:text-gray-300">
								{field.label}{#if field.unit}&nbsp;<span class="text-xs text-gray-400">({field.unit})</span>{/if}
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
								class="w-24 rounded-md border border-primary/25 bg-primary/5 px-3 py-2 text-center text-gray-900 placeholder:text-gray-400 dark:border-primary/30 dark:bg-primary/10 dark:text-white dark:placeholder:text-gray-500 disabled:opacity-50"
							/>
						</div>
						<p class="mt-0.5 text-xs leading-snug text-gray-400 dark:text-gray-500">{field.tooltip}</p>
					</div>
				{/each}
			</div>
		</div>
	</SlideOver>
</div>
{/if}
