<script lang="ts">
	import { expand, panel, reveal } from '$lib/transitions';
	import { onMount } from 'svelte';
	import LoadState from '$lib/components/LoadState.svelte';
	import SkeletonCard from '$lib/components/SkeletonCard.svelte';
	import { fetchSettings, saveArmConfig } from '$lib/api/settings';
	import type { SettingsData } from '$lib/api/settings';
	import type { DriveView as Drive, DriveDiagnosticResponse, SessionView, SettingsGroup } from '$lib/types/api.gen';
	import ConfigSchemaField from '$lib/components/settings/ConfigSchemaField.svelte';
	import SchemaConfigForm from '$lib/components/settings/SchemaConfigForm.svelte';
	import { theme, toggleTheme } from '$lib/stores/theme';
	import { colorScheme, COLOR_SCHEMES, schemeLocksMode, allSchemes, loadThemesFromApi } from '$lib/stores/colorScheme';
	import { uploadTheme, deleteTheme as deleteThemeApi } from '$lib/api/themes';
	import { createPollingStore } from '$lib/stores/polling';
	import { fetchDrives, fetchDriveDiagnostic, rescanDrives } from '$lib/api/drives';
	import { fetchSessions } from '$lib/api/sessions';
	import DriveCard from '$lib/components/DriveCard.svelte';
	import { restartArm, restartTranscoder } from '$lib/api/system';
	import { fetchImageCacheStats, clearImageCache, type ImageCacheStats } from '$lib/api/maintenance';
	import ConfirmDialog from '$lib/components/ConfirmDialog.svelte';
	import SystemHealth from '$lib/components/settings/SystemHealth.svelte';
	import { transcoderEnabled } from '$lib/stores/config';
	import NotificationsTab from '$lib/components/notifications/NotificationsTab.svelte';
	import Toggle from '$lib/components/notifications/Toggle.svelte';
	import ToastHost from '$lib/components/ToastHost.svelte';
	import DiagnosticsSection from '$lib/components/DiagnosticsSection.svelte';
	import SessionsArea from '$lib/components/sessions/SessionsArea.svelte';
	import UsersCard from '$lib/components/settings/UsersCard.svelte';

	let settings = $state<SettingsData | null>(null);
	let settingsLoading = $state(true);
	let settingsError = $state<Error | null>(null);

	// --- Restart state ---
	let armRestarting = $state(false);
	let armRestartFeedback = $state<{ type: 'success' | 'error'; message: string } | null>(null);
	let tcRestarting = $state(false);
	let tcRestartFeedback = $state<{ type: 'success' | 'error'; message: string } | null>(null);

	async function handleRestart(service: 'arm' | 'transcoder') {
		const label = service === 'arm' ? 'ARM ripping service' : 'Transcoder service';
		const warning = service === 'arm'
			? 'Restart the ARM ripping service? Active rips will be interrupted.'
			: 'Restart the transcoder service? Active transcodes will be interrupted.';
		if (!confirm(warning)) return;

		if (service === 'arm') {
			armRestarting = true;
			armRestartFeedback = null;
		} else {
			tcRestarting = true;
			tcRestartFeedback = null;
		}

		try {
			const fn = service === 'arm' ? restartArm : restartTranscoder;
			await fn();
			const fb = { type: 'success' as const, message: `${label} is restarting` };
			if (service === 'arm') armRestartFeedback = fb;
			else tcRestartFeedback = fb;
			setTimeout(() => {
				if (service === 'arm') { armRestarting = false; armRestartFeedback = null; }
				else { tcRestarting = false; tcRestartFeedback = null; }
			}, 5000);
		} catch {
			const fb = { type: 'error' as const, message: `Failed to restart ${label}` };
			if (service === 'arm') { armRestartFeedback = fb; armRestarting = false; }
			else { tcRestartFeedback = fb; tcRestarting = false; }
		}
	}

	// --- Tab state ---
	type Tab = string;
	// Non-config screen-tabs (their own bespoke UI).
	const screenTabs = ['sessions', 'transcoding', 'notifications', 'appearance', 'drives', 'system'] as const;
	// Config-group tabs derived from the backend schema. Metadata + Ripping have
	// no bespoke screen-tab home → render as their own tabs. (Transcoding/
	// Notifications single toggles fold into the existing transcoding/notifications
	// tabs; System read-only rows fold into the system tab — see template.)
	const configGroupNames = ['Metadata', 'Ripping'] as const;
	const configGroups = $derived(
		(settings?.schema?.groups ?? []).filter((g) => (configGroupNames as readonly string[]).includes(g.name))
	);
	// Full visible-tab list: config groups first, then screen-tabs (drop 'transcoding' when transcoder disabled).
	const visibleTabs = $derived([
		...configGroups.map((g) => g.name),
		...screenTabs.filter((t) => t !== 'transcoding' || $transcoderEnabled),
	]);

	// Schema groups by name, for the template tab bodies.
	function group(name: string): SettingsGroup | undefined {
		return (settings?.schema?.groups ?? []).find((g) => g.name === name);
	}
	const metaGroup = $derived(group('Metadata'));
	const rippingGroup = $derived(group('Ripping'));
	const transcodingGroup = $derived(group('Transcoding'));
	const systemGroup = $derived(group('System'));

	// Nicer labels for the screen-tab ids; config-group tabs use their group name.
	const TAB_LABELS: Record<string, string> = {
		sessions: 'Sessions',
		transcoding: 'Transcoding',
		notifications: 'Notifications',
		appearance: 'Appearance',
		drives: 'Drives',
		system: 'System',
	};
	function tabLabel(id: string): string {
		return TAB_LABELS[id] ?? id;
	}

	function parseHash(): Tab {
		if (typeof window === 'undefined') return 'Metadata';
		const hash = window.location.hash.replace('#', '');
		const tabPart = hash.split('/')[0];
		// Validate the hash tab against the known-valid set: the static
		// config-group tabs (group names, not knowable from the schema at parse
		// time but fixed in this file) plus the bespoke screen-tabs. A stale or
		// legacy hash (e.g. an old #music/#ripping bookmark) falls back to
		// 'Metadata' instead of leaving the content pane blank.
		const allowed = [...configGroupNames, ...screenTabs] as readonly string[];
		return allowed.includes(tabPart) ? tabPart : 'Metadata';
	}

	let activeTab = $state<Tab>(parseHash());

	// --- Drives polling store ---
	const drives = createPollingStore(fetchDrives, [] as Drive[], 10000);
	const driveError = drives.error;

	let driveSessions = $state<SessionView[]>([]);

	async function loadDriveSessions() {
		if (driveSessions.length > 0) return;
		try {
			driveSessions = await fetchSessions();
		} catch {
			// non-fatal: the Start-rip session picker just stays empty
		}
	}

	// --- Drive diagnostics ---
	let diagRunning = $state(false);
	let diagResult = $state<DriveDiagnosticResponse | null>(null);
	let diagError = $state<string | null>(null);
	let diagOpen = $state(false);
	let rescanning = $state(false);
	let diagLastRun = $state<string | null>(null);

	async function runDiagnostic() {
		if (diagRunning) return;
		diagRunning = true;
		diagError = null;
		try {
			diagResult = await fetchDriveDiagnostic();
			diagLastRun = new Date().toLocaleTimeString();
			diagOpen = true;
		} catch (e) {
			diagError = e instanceof Error ? e.message : 'Diagnostic failed';
			diagResult = null;
		} finally {
			diagRunning = false;
		}
	}

	// --- Theme management ---
	let themeUploading = $state(false);
	let themeFeedback = $state<{ type: 'success' | 'error'; message: string } | null>(null);
	let themeJsonFile = $state<File | null>(null);
	let themeName = $state('');
	let themeCssText = $state('');

	// --- Image cache state ---
	let cacheStats = $state<ImageCacheStats | null>(null);
	let cacheLoading = $state(false);
	let cacheBusy = $state(false);
	let cacheConfirmOpen = $state(false);
	let cacheFeedback = $state<{ type: 'success' | 'error'; message: string } | null>(null);

	async function loadCacheStats() {
		cacheLoading = true;
		try { cacheStats = await fetchImageCacheStats(); }
		catch { cacheStats = null; }
		cacheLoading = false;
	}

	async function handleClearCache() {
		cacheBusy = true;
		cacheConfirmOpen = false;
		try {
			const result = await clearImageCache();
			const cleared = result.cleared ?? 0;
			const freedMb = ((result.freed_bytes ?? 0) / 1048576).toFixed(1);
			cacheFeedback = { type: 'success', message: `Cleared ${cleared} cached image${cleared !== 1 ? 's' : ''} (${freedMb} MB)` };
			cacheStats = await fetchImageCacheStats();
		} catch (e) {
			cacheFeedback = { type: 'error', message: e instanceof Error ? e.message : 'Failed to clear cache' };
		}
		cacheBusy = false;
	}

	async function handleThemeUpload() {
		if (!themeJsonFile) return;
		const name = themeName.trim();
		if (!name) {
			themeFeedback = { type: 'error', message: 'Theme name is required' };
			return;
		}
		themeUploading = true;
		themeFeedback = null;
		try {
			const text = await themeJsonFile.text();
			const data = JSON.parse(text);
			// Override label and derive id from the name field
			data.label = name;
			data.id = name.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '');
			if (!data.id || !data.tokens) {
				throw new Error('Invalid theme: missing required fields (tokens)');
			}
			// Re-create the file with patched data
			const patched = new File([JSON.stringify(data)], `${data.id}.json`, { type: 'application/json' });
			await uploadTheme(patched, themeCssText);
			await loadThemesFromApi();
			themeFeedback = { type: 'success', message: `Theme "${data.label}" uploaded` };
			themeJsonFile = null;
			themeName = '';
			themeCssText = '';
		} catch (e) {
			themeFeedback = { type: 'error', message: e instanceof Error ? e.message : 'Upload failed' };
		} finally {
			themeUploading = false;
		}
	}

	function handleJsonFileSelect(event: Event) {
		const input = event.target as HTMLInputElement;
		themeJsonFile = input.files?.[0] ?? null;
	}

	async function handleThemeDelete(id: string, label: string) {
		if (!confirm(`Delete user theme "${label}"?`)) return;
		themeFeedback = null;
		try {
			await deleteThemeApi(id);
			await loadThemesFromApi();
			if ($colorScheme === id) $colorScheme = 'blue';
			themeFeedback = { type: 'success', message: `Theme "${label}" deleted` };
		} catch (e) {
			themeFeedback = { type: 'error', message: e instanceof Error ? e.message : 'Delete failed' };
		}
	}

	function triggerDownload(blob: Blob, filename: string) {
		const url = URL.createObjectURL(blob);
		const a = document.createElement('a');
		a.href = url;
		a.download = filename;
		a.click();
		URL.revokeObjectURL(url);
	}

	async function handleThemeDownload(id: string) {
		const enc = encodeURIComponent(id);
		try {
			// Download JSON
			const jsonRes = await fetch(`/api/themes/${enc}/download`);
			if (jsonRes.ok) {
				const jsonBlob = await jsonRes.blob();
				triggerDownload(jsonBlob, `${id}.json`);
			}
			// Download CSS if the theme has any
			const cssRes = await fetch(`/api/themes/${enc}/css`);
			if (cssRes.ok) {
				const cssBlob = await cssRes.blob();
				triggerDownload(cssBlob, `${id}.css`);
			}
		} catch { /* download failed silently */ }
	}

	// Set to true while we are mutating window.location.hash ourselves,
	// so the hashchange listener can skip the work setTab already did
	// (otherwise tab clicks scroll twice — once here, once in the listener).
	let programmaticHashChange = false;

	function setTab(tab: Tab) {
		activeTab = tab;
		programmaticHashChange = true;
		window.location.hash = tab;
		if (tab === 'appearance') loadCacheStats();
		if (tab === 'drives') loadDriveSessions();
		// Reset scroll to top when switching tabs
		document.querySelector('main')?.scrollTo(0, 0);
	}

	onMount(() => {
		// Rescan drives to pick up hardware info (model, serial) that
		// may not have been available at container startup.
		rescanDrives().catch(() => {}).then(() => drives.start());
		loadSettings();
		// Handle initial hash tab (trigger side effects)
		if (activeTab === 'appearance') loadCacheStats();
		if (activeTab === 'drives') loadDriveSessions();
		function onHashChange() {
			if (programmaticHashChange) {
				programmaticHashChange = false;
				return;
			}
			const tab = parseHash();
			activeTab = tab;
			if (tab === 'appearance') loadCacheStats();
			if (tab === 'drives') loadDriveSessions();
			// Reset scroll to top when switching tabs
			document.querySelector('main')?.scrollTo(0, 0);
		}
		window.addEventListener('hashchange', onHashChange);
		return () => { drives.stop(); window.removeEventListener('hashchange', onHashChange); };
	});

	async function loadSettings() {
		settingsLoading = true;
		settingsError = null;
		try {
			settings = await fetchSettings();
		} catch (e) {
			settingsError = e instanceof Error ? e : new Error('Failed to load settings');
		} finally {
			settingsLoading = false;
		}
	}

	// The notifications master toggle auto-saves on change (no Save button): PATCH
	// immediately, optimistically flip settings.config so the channels UI shows/
	// hides at once, and roll back on failure.
	let notifSaving = $state(false);
	async function toggleNotifications(next: boolean) {
		if (!settings || notifSaving) return;
		const prev = Boolean(settings.config?.notifications_enabled);
		settings = { ...settings, config: { ...settings.config, notifications_enabled: next } };
		notifSaving = true;
		try {
			await saveArmConfig({ notifications_enabled: next });
		} catch {
			settings = { ...settings, config: { ...settings.config, notifications_enabled: prev } };
		} finally {
			notifSaving = false;
		}
	}

	function clearFeedback(setter: (v: null) => void) {
		setTimeout(() => setter(null), 4000);
	}

</script>

<svelte:head>
	<title>ARM - Settings</title>
</svelte:head>

<div in:panel class="space-y-6 pb-20">
	<h1 class="text-2xl font-bold text-gray-900 dark:text-white">Settings</h1>

	<LoadState
		data={settings}
		loading={settingsLoading}
		error={settingsError}
		transitionKey={`settings-${activeTab}`}
	>
		{#snippet loadingSlot()}
			<div class="space-y-4">
				<SkeletonCard lines={5} />
				<SkeletonCard lines={4} />
			</div>
		{/snippet}
		{#snippet ready(_)}
		{@const settings = _}
		<!-- Tab Bar -->
		{@const tabClass = (tab: string) => `whitespace-nowrap border-b-2 px-1 py-2.5 text-sm font-medium transition-colors ${activeTab === tab ? 'border-primary text-primary-text dark:border-primary-text-dark dark:text-primary-text-dark' : 'border-transparent text-gray-500 hover:border-primary/30 hover:text-gray-700 dark:text-gray-400 dark:hover:border-primary/30 dark:hover:text-gray-300'}`}
		<!-- overflow-y-hidden prevents the 1px vertical scroll that
			 -mb-px + border-b-2 would otherwise trigger inside overflow-x-auto.
			 mb-2 adds breathing room below the tab strip on top of the
			 outer space-y-6 - tabs feel cramped against headings otherwise. -->
		<div class="mb-2 overflow-x-auto overflow-y-hidden border-b border-primary/20 dark:border-primary/20">
			<nav class="-mb-px flex gap-4" aria-label="Settings tabs">
				{#each visibleTabs as tab}
					<button type="button" onclick={() => setTab(tab)} class={tabClass(tab)}>{tabLabel(tab)}</button>
				{/each}
			</nav>
		</div>

		<!-- Metadata config tab (schema-driven) -->
		{#if activeTab === 'Metadata' && metaGroup}
			<SchemaConfigForm group={metaGroup} config={settings.config} />
		{/if}

		<!-- Ripping config tab (schema-driven) -->
		{#if activeTab === 'Ripping' && rippingGroup}
			<SchemaConfigForm group={rippingGroup} config={settings.config} />
		{/if}

		<!-- Transcoding Tab (single auto_transcode_on_idle toggle, schema-driven) -->
		{#if activeTab === 'transcoding' && $transcoderEnabled && transcodingGroup}
			<SchemaConfigForm group={transcodingGroup} config={settings.config} />
		{/if}

		{#if activeTab === 'sessions'}
			<SessionsArea />
		{/if}

		<!-- Notifications Tab -->
		{#if activeTab === 'notifications'}
			<div class="space-y-4">
				<div>
					<h2 class="text-lg font-semibold text-gray-900 dark:text-white">Notifications</h2>
					<p class="text-sm text-gray-500 dark:text-gray-400">
						Manage notification channels - Discord, Slack, webhooks, scripts, and more.
					</p>
				</div>
				<label class="flex items-center gap-3 text-sm">
					<Toggle
						checked={Boolean(settings.config?.notifications_enabled)}
						label="Enable notifications"
						onchange={toggleNotifications}
					/>
					<span class="font-medium text-gray-900 dark:text-white">Enable notifications</span>
					<span class="text-xs text-gray-500 dark:text-gray-400">(changes save automatically)</span>
				</label>
				{#if settings.config?.notifications_enabled}
					<NotificationsTab />
				{:else}
					<p class="rounded-lg border border-primary/15 bg-page px-4 py-6 text-center text-sm text-gray-500 dark:border-primary/20 dark:bg-primary/5 dark:text-gray-400">
						Notifications are disabled. Enable the toggle above to manage channels.
					</p>
				{/if}
			</div>
		{/if}

		<!-- System Info Tab -->
		{#if activeTab === 'system'}
			<div in:reveal class="space-y-6">
				<h2 class="text-lg font-semibold text-gray-900 dark:text-white">System</h2>

				<!-- Health check (API keys + path permissions) -->
				<SystemHealth />

				<!-- Read-only infra configuration (schema-driven) -->
				{#if systemGroup}
					<section in:reveal class="space-y-4">
						<h3 class="text-lg font-semibold text-gray-900 dark:text-white">Configuration (read-only)</h3>
						<div class="space-y-4 rounded-lg border border-primary/20 bg-surface p-4 dark:border-primary/20 dark:bg-surface-dark">
							{#each systemGroup.fields as f (f.key)}
								<ConfigSchemaField field={f} value={(settings.config as Record<string, unknown>)?.[f.key] ?? settings.infra?.[f.key]} />
							{/each}
						</div>
					</section>
				{/if}
			</div>

			<!-- Users -->
			<section in:reveal class="mt-6">
				<UsersCard />
			</section>

			<!-- Service Control -->
			<section in:reveal class="mt-6">
				<h2 class="mb-4 text-lg font-semibold text-gray-900 dark:text-white">Service Control</h2>
				<div class="space-y-3">
					<!-- ARM Restart -->
					<div class="rounded-lg border border-red-200 bg-red-50/50 p-4 dark:border-red-800 dark:bg-red-900/10">
						<div class="flex items-center justify-between">
							<div>
								<p class="text-sm font-medium text-gray-900 dark:text-white">Restart ARM Service</p>
								<p class="text-xs text-gray-500 dark:text-gray-400">Restarts the ARM ripping service. Active rips will be interrupted.</p>
								{#if armRestartFeedback}
									<p in:reveal class="mt-1 text-xs {armRestartFeedback.type === 'success' ? 'text-green-600 dark:text-green-400' : 'text-red-600 dark:text-red-400'}">{armRestartFeedback.message}</p>
								{/if}
							</div>
							<button
								type="button"
								disabled={armRestarting}
								onclick={() => handleRestart('arm')}
								class="rounded-lg bg-red-600 px-4 py-2 text-sm font-medium text-white hover:bg-red-700 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
							>
								{armRestarting ? 'Restarting...' : 'Restart'}
							</button>
						</div>
					</div>
					<!-- Transcoder Restart -->
					{#if $transcoderEnabled}
					<div class="rounded-lg border border-red-200 bg-red-50/50 p-4 dark:border-red-800 dark:bg-red-900/10">
						<div class="flex items-center justify-between">
							<div>
								<p class="text-sm font-medium text-gray-900 dark:text-white">Restart Transcoder Service</p>
								<p class="text-xs text-gray-500 dark:text-gray-400">Restarts the transcoder service. Active transcodes will be interrupted.</p>
								{#if tcRestartFeedback}
									<p in:reveal class="mt-1 text-xs {tcRestartFeedback.type === 'success' ? 'text-green-600 dark:text-green-400' : 'text-red-600 dark:text-red-400'}">{tcRestartFeedback.message}</p>
								{/if}
							</div>
							<button
								type="button"
								disabled={tcRestarting}
								onclick={() => handleRestart('transcoder')}
								class="rounded-lg bg-red-600 px-4 py-2 text-sm font-medium text-white hover:bg-red-700 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
							>
								{tcRestarting ? 'Restarting...' : 'Restart'}
							</button>
						</div>
					</div>
					{/if}
				</div>
			</section>

			<!-- Diagnostics (moved here from the standalone Diagnostics tab) -->
			<section class="mt-6">
				<DiagnosticsSection />
			</section>
		{/if}

		<!-- Appearance Tab -->
		{#if activeTab === 'appearance'}
			<h2 class="mb-4 text-lg font-semibold text-gray-900 dark:text-white">Appearance</h2>
			<section class="space-y-6">
				<!-- Feedback toast -->
				{#if themeFeedback}
					<div class="rounded-lg border p-3 text-sm {themeFeedback.type === 'success' ? 'border-green-200 bg-green-50 text-green-700 dark:border-green-800 dark:bg-green-900/20 dark:text-green-400' : 'border-red-200 bg-red-50 text-red-700 dark:border-red-800 dark:bg-red-900/20 dark:text-red-400'}">
						{themeFeedback.message}
					</div>
				{/if}

				<!-- Built-in Themes -->
				<div class="rounded-lg border border-primary/20 bg-surface p-6 shadow-xs dark:border-primary/20 dark:bg-surface-dark">
					<h3 class="mb-1 text-base font-semibold text-gray-900 dark:text-white">Color Scheme</h3>
					<p class="mb-4 text-sm text-gray-500 dark:text-gray-400">Choose an accent color for buttons, links, and highlights throughout the UI.</p>
					<div class="flex flex-wrap gap-3">
						{#each $allSchemes.filter(s => s.builtin !== false) as scheme}
							<button
								type="button"
								onclick={() => ($colorScheme = scheme.id)}
								class="group relative flex flex-col items-center gap-1.5 rounded-lg border-2 px-4 py-3 transition-colors
									{$colorScheme === scheme.id
									? 'border-primary bg-primary-light-bg dark:border-primary-text-dark dark:bg-primary-light-bg-dark/20'
									: 'border-primary/15 hover:border-primary/30 dark:border-primary/15 dark:hover:border-primary/30'}"
							>
								<span class="h-8 w-8 rounded-full" style="background-color: {scheme.swatch}"></span>
								<span class="text-xs font-medium text-gray-700 dark:text-gray-300">{scheme.label}</span>
								{#if scheme.description}
									<span class="absolute -top-8 left-1/2 -translate-x-1/2 whitespace-nowrap rounded bg-gray-800 px-2 py-1 text-[10px] text-white opacity-0 transition-opacity group-hover:opacity-100 dark:bg-gray-700">{scheme.description}</span>
								{/if}
							</button>
						{/each}
					</div>
					<div class="mt-3 flex gap-2">
						<button
							type="button"
							onclick={() => handleThemeDownload($colorScheme)}
							class="inline-flex items-center gap-1 rounded-md bg-primary/10 px-3 py-1.5 text-xs font-medium text-primary-text transition-colors hover:bg-primary/20 dark:text-primary-text-dark"
						>
							<svg class="h-3.5 w-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" /></svg>
							Export current theme
						</button>
					</div>
				</div>

				<!-- User Themes -->
				{#if $allSchemes.filter(s => s.builtin === false).length > 0}
					<div class="rounded-lg border border-primary/20 bg-surface p-6 shadow-xs dark:border-primary/20 dark:bg-surface-dark">
						<h3 class="mb-1 text-base font-semibold text-gray-900 dark:text-white">User Themes</h3>
						<p class="mb-4 text-sm text-gray-500 dark:text-gray-400">Custom themes loaded from your themes directory.</p>
						<div class="flex flex-wrap gap-3">
							{#each $allSchemes.filter(s => s.builtin === false) as scheme}
								<div class="relative">
									<button
										type="button"
										onclick={() => ($colorScheme = scheme.id)}
										class="flex flex-col items-center gap-1.5 rounded-lg border-2 px-4 py-3 transition-colors
											{$colorScheme === scheme.id
											? 'border-primary bg-primary-light-bg dark:border-primary-text-dark dark:bg-primary-light-bg-dark/20'
											: 'border-primary/15 hover:border-primary/30 dark:border-primary/15 dark:hover:border-primary/30'}"
									>
										<span class="h-8 w-8 rounded-full" style="background-color: {scheme.swatch}"></span>
										<span class="text-xs font-medium text-gray-700 dark:text-gray-300">{scheme.label}</span>
										{#if scheme.author}
											<span class="text-[10px] text-gray-400">by {scheme.author}</span>
										{/if}
									</button>
									<div class="absolute -right-1 -top-1 flex gap-0.5">
										<button
											type="button"
											onclick={() => handleThemeDownload(scheme.id)}
											class="rounded-full bg-gray-200 p-0.5 text-gray-500 hover:bg-gray-300 dark:bg-gray-700 dark:text-gray-400 dark:hover:bg-gray-600"
											title="Download"
										>
											<svg class="h-3 w-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" /></svg>
										</button>
										<button
											type="button"
											onclick={() => handleThemeDelete(scheme.id, scheme.label)}
											class="rounded-full bg-red-100 p-0.5 text-red-500 hover:bg-red-200 dark:bg-red-900/30 dark:text-red-400 dark:hover:bg-red-900/50"
											title="Delete"
										>
											<svg class="h-3 w-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" /></svg>
										</button>
									</div>
								</div>
							{/each}
						</div>
					</div>
				{/if}

				<!-- Upload Theme -->
				<div class="rounded-lg border border-primary/20 bg-surface p-6 shadow-xs dark:border-primary/20 dark:bg-surface-dark">
					<h3 class="mb-1 text-base font-semibold text-gray-900 dark:text-white">Import Theme</h3>
					<p class="mb-4 text-sm text-gray-500 dark:text-gray-400">Upload a theme JSON file and optional custom CSS.</p>
					<div class="space-y-4">
						<!-- Theme name -->
						<div>
							<label for="theme-name-input" class="mb-1 block text-sm font-medium text-gray-700 dark:text-gray-300">Theme Name <span class="text-red-500">*</span></label>
							<input
								id="theme-name-input"
								type="text"
								bind:value={themeName}
								placeholder="My Theme"
								disabled={themeUploading}
								class="w-full rounded-lg border border-primary/25 bg-primary/5 px-3 py-2 text-sm dark:border-primary/30 dark:bg-primary/10 dark:text-white"
							/>
						</div>
						<!-- JSON file picker -->
						<div>
							<span class="mb-1 block text-sm font-medium text-gray-700 dark:text-gray-300">Theme JSON <span class="text-red-500">*</span></span>
							<label class="inline-flex cursor-pointer items-center gap-2 rounded-lg bg-primary/10 px-4 py-2 text-sm font-medium text-primary-text transition-colors hover:bg-primary/20 dark:text-primary-text-dark">
								<svg class="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-8l-4-4m0 0L8 8m4-4v12" /></svg>
								{themeJsonFile ? themeJsonFile.name : 'Choose .json file'}
								<input type="file" accept=".json" class="hidden" onchange={handleJsonFileSelect} disabled={themeUploading} />
							</label>
						</div>
						<!-- CSS textarea -->
						<div>
							<label for="theme-css-input" class="mb-1 block text-sm font-medium text-gray-700 dark:text-gray-300">Custom CSS <span class="text-xs text-gray-400">(optional)</span></label>
							<textarea
								id="theme-css-input"
								bind:value={themeCssText}
								placeholder={'[data-scheme="my-theme"] {\n  /* custom styles */\n}'}
								rows="6"
								disabled={themeUploading}
								class="w-full rounded-lg border border-primary/25 bg-primary/5 px-3 py-2 font-mono text-sm dark:border-primary/30 dark:bg-primary/10 dark:text-white"
							></textarea>
						</div>
						<!-- Upload button -->
						<div class="flex items-center gap-3">
							<button
								type="button"
								onclick={handleThemeUpload}
								disabled={!themeJsonFile || !themeName.trim() || themeUploading}
								class="inline-flex items-center gap-2 rounded-lg bg-primary px-4 py-2 text-sm font-medium text-on-primary transition-colors hover:bg-primary-hover disabled:opacity-50"
							>
								{themeUploading ? 'Uploading...' : 'Upload Theme'}
							</button>
							{#if themeFeedback}
								<span class="text-sm {themeFeedback.type === 'success' ? 'text-green-600 dark:text-green-400' : 'text-red-600 dark:text-red-400'}">
									{themeFeedback.message}
								</span>
							{/if}
						</div>
					</div>
				</div>

				<!-- Dark Mode -->
				<div class="rounded-lg border border-primary/20 bg-surface p-6 shadow-xs dark:border-primary/20 dark:bg-surface-dark">
					<div class="flex items-center justify-between">
						<div>
							<h3 class="text-base font-semibold text-gray-900 dark:text-white">Dark Mode</h3>
							{#if $schemeLocksMode}
								<p class="text-sm text-gray-500 dark:text-gray-400">Locked by theme</p>
							{:else}
								<p class="text-sm text-gray-500 dark:text-gray-400">Toggle between light and dark mode.</p>
							{/if}
						</div>
						{#if !$schemeLocksMode}
							<div class="flex items-center gap-2">
								<button
									type="button"
									onclick={toggleTheme}
									class="relative inline-flex h-6 w-11 shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 ease-in-out
										{$theme === 'dark' ? 'bg-primary' : 'bg-primary/30 dark:bg-primary/20'}"
									role="switch"
									aria-checked={$theme === 'dark'}
									aria-label="Dark mode"
								>
									<span
										class="pointer-events-none inline-block h-5 w-5 transform rounded-full bg-white shadow ring-0 transition duration-200 ease-in-out
											{$theme === 'dark' ? 'translate-x-5' : 'translate-x-0'}"
									></span>
								</button>
								<span class="text-xs font-medium {$theme === 'dark' ? 'text-primary-text dark:text-primary-text-dark' : 'text-gray-400'}">
									{$theme === 'dark' ? 'On' : 'Off'}
								</span>
							</div>
						{/if}
					</div>
				</div>

				<!-- Image Cache -->
				<div class="rounded-lg border border-primary/20 bg-surface p-6 shadow-xs dark:border-primary/20 dark:bg-surface-dark">
					<div class="flex items-center justify-between">
						<div>
							<h3 class="text-base font-semibold text-gray-900 dark:text-white">Image Cache</h3>
							<p class="mt-1 text-sm text-gray-500 dark:text-gray-400">
								{#if cacheLoading}Loading...
								{:else if cacheStats}{cacheStats.count} cached image{cacheStats.count !== 1 ? 's' : ''} ({cacheStats.size_mb} MB)
								{:else}Unable to load cache stats
								{/if}
							</p>
						</div>
						<button type="button"
							onclick={() => (cacheConfirmOpen = true)}
							disabled={cacheBusy || !cacheStats?.count}
							class="rounded-lg px-3 py-1.5 text-sm font-medium text-red-600 hover:bg-red-500/10 disabled:opacity-50 dark:text-red-400 dark:hover:bg-red-500/15">
							Clear Cache
						</button>
					</div>
					{#if cacheFeedback}
						<p class="mt-2 text-sm {cacheFeedback.type === 'success' ? 'text-green-600 dark:text-green-400' : 'text-red-600 dark:text-red-400'}">
							{cacheFeedback.message}
						</p>
					{/if}
				</div>

				<!-- Feature request prompt -->
				<div class="flex justify-center pt-2">
					<span class="inline-flex items-center gap-1.5 rounded-full bg-primary/10 px-4 py-2 text-xs text-gray-500 dark:text-gray-400">
						<svg class="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2"><path stroke-linecap="round" stroke-linejoin="round" d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5.002 5.002 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z" /></svg>
						Not seeing what you want? Submit your feature requests on GitHub.
					</span>
				</div>
			</section>
		{/if}

		{#if activeTab === 'drives'}
			<h2 class="mb-4 text-lg font-semibold text-gray-900 dark:text-white">Drives</h2>
			<section class="space-y-6">
				{#if $driveError}
					<div class="rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-700 dark:border-red-800 dark:bg-red-900/20 dark:text-red-400">
						{$driveError}
					</div>
				{:else if $drives.length === 0}
					<p class="py-8 text-center text-gray-400">No drives detected.</p>
				{:else}
					<div class="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
						{#each $drives as drive (drive.id)}
							<DriveCard {drive} sessions={driveSessions} onupdate={() => drives.refresh()} globalDefaults={{
								prescan_cache_mb: Number(settings?.arm_config?.PRESCAN_CACHE_MB) || 1,
								prescan_timeout: Number(settings?.arm_config?.PRESCAN_TIMEOUT) || 300,
								prescan_retries: Number(settings?.arm_config?.PRESCAN_RETRIES) || 3,
								disc_enum_timeout: Number(settings?.arm_config?.DISC_ENUM_TIMEOUT) || 60,
							}} />
						{/each}
					</div>
				{/if}

				<!-- Maintenance & Diagnostics -->
				<hr class="my-2 opacity-20" />
				<div class="flex flex-wrap items-center gap-2">
					<span class="text-xs font-medium uppercase tracking-wider text-gray-500 dark:text-gray-400">Maintenance</span>
					<button
						onclick={async () => { rescanning = true; await rescanDrives(); await drives.refresh(); rescanning = false; }}
						disabled={rescanning}
						class="ml-auto rounded-lg border border-primary/20 px-3 py-1.5 text-xs font-medium text-primary-text transition-colors hover:bg-primary/10 disabled:opacity-50 dark:border-primary/20 dark:text-primary-text-dark dark:hover:bg-primary/15"
						title="Re-detect optical drives and refresh database records"
					>{rescanning ? 'Scanning...' : 'Rescan'}</button>
					<button
						onclick={async () => { rescanning = true; await rescanDrives(true); await drives.refresh(); rescanning = false; }}
						disabled={rescanning}
						class="rounded-lg border border-amber-300 px-3 py-1.5 text-xs font-medium text-amber-700 transition-colors hover:bg-amber-50 disabled:opacity-50 dark:border-amber-700 dark:text-amber-400 dark:hover:bg-amber-900/20"
						title="Delete all stale drive records and re-detect from hardware"
					>{rescanning ? 'Scanning...' : 'Force Rescan'}</button>
				</div>
				<div data-diag>
					<button
						onclick={() => { diagOpen = !diagOpen; }}
						class="flex w-full items-center gap-2 rounded-lg border border-primary/15 bg-primary/5 px-3.5 py-2.5 text-sm font-medium text-primary-text transition-colors hover:bg-primary/10 dark:border-primary/15 dark:text-primary-text-dark dark:hover:bg-primary/15"
					>
						<svg class="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
							<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z" />
						</svg>
						Udev & Drive Diagnostics
						<svg class="ml-auto h-4 w-4 transition-transform duration-200 {diagOpen ? 'rotate-180' : ''}" fill="none" stroke="currentColor" viewBox="0 0 24 24">
							<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7" />
						</svg>
					</button>

					{#if diagOpen}
						<div class="mt-2.5 rounded-lg border border-primary/10 bg-white/[0.02] p-3 dark:border-primary/10" transition:expand>
							<div class="mb-2.5 flex items-center justify-between">
								<button
									onclick={runDiagnostic}
									disabled={diagRunning}
									class="inline-flex items-center gap-2 rounded-lg bg-primary/15 px-3.5 py-1.5 text-sm font-medium text-primary-text transition-colors hover:bg-primary/25 disabled:opacity-50 dark:text-primary-text-dark dark:hover:bg-primary/30"
								>
									<svg class="h-4 w-4 {diagRunning ? 'animate-spin' : ''}" fill="none" stroke="currentColor" viewBox="0 0 24 24">
										<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
									</svg>
									{diagRunning ? 'Running...' : 'Run Check'}
								</button>
								{#if diagLastRun}
									<span class="text-[10px] text-gray-400 dark:text-gray-500">Last run: {diagLastRun}</span>
								{/if}
								{#if diagError}
									<span class="text-sm text-red-600 dark:text-red-400">{diagError}</span>
								{/if}
							</div>

							{#if diagResult}
								{@const unhealthy = diagResult.drives.filter(d => !d.healthy || d.notes.length > 0)}
								<!-- Status bar -->
								<div class="mb-2 flex flex-wrap items-center gap-3 rounded-lg border px-3 py-2 text-xs
									{unhealthy.length > 0
										? 'border-amber-500/15 bg-amber-500/5'
										: 'border-green-500/15 bg-green-500/5'}">
									<span class="text-gray-500 dark:text-gray-400">
										{diagResult.drives.length} drive{diagResult.drives.length !== 1 ? 's' : ''}
									</span>
									<span class="font-medium {unhealthy.length > 0 ? 'text-amber-600 dark:text-amber-400' : 'text-green-600 dark:text-green-400'}">
										{unhealthy.length > 0 ? 'Issues Found' : 'All OK'}
									</span>
								</div>

								<!-- Per-drive issues only -->
								{#each unhealthy as diag}
									<div class="mb-1.5 rounded-lg border border-amber-500/15 bg-amber-500/5 p-2.5">
										{#each diag.notes as note}
											<div class="flex items-start gap-1.5 text-xs">
												<svg class="mt-0.5 h-3 w-3 flex-shrink-0 text-amber-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
													<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-2.5L13.732 4c-.77-.833-1.964-.833-2.732 0L4.082 16.5c-.77.833.192 2.5 1.732 2.5z" />
												</svg>
												<span class="text-amber-700 dark:text-amber-400">
													<span class="font-medium">{diag.id}</span> - {note}
												</span>
											</div>
										{/each}
										{#if diag.notes.length === 0 && !diag.healthy}
											<div class="text-xs text-amber-700 dark:text-amber-400">
												<span class="font-medium">{diag.id}</span> - unhealthy
											</div>
										{/if}
									</div>
								{/each}
							{:else if !diagRunning}
								<p class="text-center text-xs text-gray-400 dark:text-gray-500">Click "Run Check" to scan drives and udev configuration.</p>
							{/if}
						</div>
					{/if}
				</div>
			</section>
		{/if}

		{/snippet}
	</LoadState>
</div>

<ConfirmDialog
	open={cacheConfirmOpen}
	title="Clear Image Cache"
	message="Delete all cached poster images? They will be re-fetched on next view."
	confirmLabel="Clear"
	variant="danger"
	onconfirm={handleClearCache}
	oncancel={() => (cacheConfirmOpen = false)}
/>

<ToastHost />
