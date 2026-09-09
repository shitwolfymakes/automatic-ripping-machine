<script lang="ts">
	import { slide } from 'svelte/transition';
	import { onMount } from 'svelte';
	import { reveal } from '$lib/transitions';
	import LoadState from '$lib/components/LoadState.svelte';
	import SkeletonCard from '$lib/components/SkeletonCard.svelte';
	import { fetchSettings, saveArmConfig } from '$lib/api/settings';
	import type { SettingsData } from '$lib/api/settings';
	import type { DriveView as Drive, DriveDiagnosticResponse, SessionView, SettingsGroup } from '$lib/types/api.gen';
	import ConfigSchemaField from '$lib/components/settings/ConfigSchemaField.svelte';
	import SchemaConfigForm from '$lib/components/settings/SchemaConfigForm.svelte';
	import { theme, toggleTheme } from '$lib/stores/theme';
	import { colorScheme, COLOR_SCHEMES, schemeLocksMode, allSchemes, loadThemesFromApi } from '$lib/stores/colorScheme';
	import { deleteTheme as deleteThemeApi } from '$lib/api/themes';
	import { createPollingStore } from '$lib/stores/polling';
	import { fetchDrives, fetchDriveDiagnostic, rescanDrives } from '$lib/api/drives';
	import { partitionDrives } from '$lib/utils/drives';
	import { formatDateTime } from '$lib/utils/format';
	import { fetchSessions } from '$lib/api/sessions';
	import DriveCard from '$lib/components/DriveCard.svelte';
	import DriveMaintenance from '$lib/components/DriveMaintenance.svelte';
	import DriveLifecycleLists from '$lib/components/DriveLifecycleLists.svelte';
	import InterfaceSettings from '$lib/components/settings/InterfaceSettings.svelte';
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
	import Glyph from '$lib/components/Glyph.svelte';

	let settings = $state<SettingsData | null>(null);
	let settingsLoading = $state(true);
	let settingsError = $state<Error | null>(null);

	// --- Tab state ---
	type Tab = string;
	// Non-config screen-tabs (their own bespoke UI).
	const screenTabs = ['sessions', 'transcoding', 'notifications', 'interface', 'themes', 'drives', 'users', 'system'] as const;
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
		interface: 'Interface',
		themes: 'Themes',
		drives: 'Drives',
		users: 'Users',
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
		if (tabPart === 'appearance') return 'themes'; // pre-rename bookmarks and links
		return allowed.includes(tabPart) ? tabPart : 'Metadata';
	}

	let activeTab = $state<Tab>(parseHash());

	// Deep link: `#<tab>/<field key>` (e.g. the header's Key dot points at
	// #Metadata/makemkv_key). The field is scrolled into view, focused and
	// briefly highlighted once its tab has rendered.
	function parseHashField(): string | null {
		if (typeof window === 'undefined') return null;
		const part = window.location.hash.replace('#', '').split('/')[1];
		return part ? decodeURIComponent(part) : null;
	}
	let pendingField = $state<string | null>(parseHashField());

	$effect(() => {
		const key = pendingField;
		if (!key || !settings) return;
		const el = document.getElementById(`setting-${key}`);
		if (!el) return;
		pendingField = null;
		el.scrollIntoView({ block: 'center' });
		el.querySelector<HTMLElement>('input, select, textarea')?.focus({ preventScroll: true });
		el.classList.add('settings-field-highlight');
		setTimeout(() => el.classList.remove('settings-field-highlight'), 1600);
	});

	// --- Drives polling store ---
	const drives = createPollingStore(fetchDrives, [] as Drive[], 10000);
	const driveError = drives.error;
	let parts = $derived(partitionDrives($drives));

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
	let themeFeedback = $state<{ type: 'success' | 'error'; message: string } | null>(null);

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

	// Set to true while we are mutating window.location.hash ourselves,
	// so the hashchange listener can skip the work setTab already did
	// (otherwise tab clicks scroll twice — once here, once in the listener).
	let programmaticHashChange = false;

	function setTab(tab: Tab) {
		activeTab = tab;
		programmaticHashChange = true;
		window.location.hash = tab;
		if (tab === 'themes') loadCacheStats();
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
		if (activeTab === 'themes') loadCacheStats();
		if (activeTab === 'drives') loadDriveSessions();
		function onHashChange() {
			if (programmaticHashChange) {
				programmaticHashChange = false;
				return;
			}
			const tab = parseHash();
			activeTab = tab;
			pendingField = parseHashField();
			if (tab === 'themes') loadCacheStats();
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

<div class="stack stack-lg settings-page">
	<h1 class="page-title">Settings</h1>

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
		<!-- settings-page-tabs adds breathing room below the tab strip (mb-2)
			 and clips the 1px vertical scroll .tabs' own border-bottom can
			 trigger inside its overflow-x-auto (overflow-y: hidden) - tabs feel
			 cramped against headings otherwise. -->
		<!-- role="tablist" sits on an inner <div>, not the <nav> itself: a
			 <nav> is a non-interactive landmark and cannot carry the
			 interactive tablist role (svelte a11y
			 a11y_no_noninteractive_element_to_interactive_role). This is the
			 same shape SessionsArea.svelte uses. The <nav aria-label="Settings
			 tabs"> wrapper is kept because the parity harness selects the strip
			 with nav[aria-label="Settings tabs"]; it is an unstyled block box,
			 so the inner div reproduces the previous nav's own box exactly. -->
		<nav aria-label="Settings tabs">
			<div class="tabs settings-page-tabs" role="tablist">
				{#each visibleTabs as tab}
					<button type="button" role="tab" onclick={() => setTab(tab)} class="tabs-tab" aria-selected={activeTab === tab}>{tabLabel(tab)}</button>
				{/each}
			</div>
		</nav>

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
			<div class="stack">
				<div>
					<h2 class="settings-page-section-title">Notifications</h2>
					<p class="settings-page-description">
						Manage notification channels - Discord, Slack, webhooks, scripts, and more.
					</p>
				</div>
				<label class="field field-row settings-page-notif-toggle-row">
					<Toggle
						checked={Boolean(settings.config?.notifications_enabled)}
						label="Enable notifications"
						onchange={toggleNotifications}
					/>
					<span class="field-label">Enable notifications</span>
					<span class="settings-page-inline-hint">(changes save automatically)</span>
				</label>
				{#if settings.config?.notifications_enabled}
					<NotificationsTab />
				{:else}
					<p class="panel-section settings-page-notifications-off">
						Notifications are disabled. Enable the toggle above to manage channels.
					</p>
				{/if}
			</div>
		{/if}

		<!-- Users Tab: account management (admin password + guest access) -->
		{#if activeTab === 'users'}
			<div in:reveal class="stack stack-lg">
				<h2 class="settings-page-section-title">Users</h2>
				<UsersCard />
			</div>
		{/if}

		<!-- System Info Tab -->
		{#if activeTab === 'system'}
			<div class="stack stack-lg">
				<h2 class="settings-page-section-title">System</h2>

				<!-- Health check (API keys + path permissions) -->
				<SystemHealth />

				<!-- Read-only infra configuration (schema-driven) -->
				{#if systemGroup}
					<section class="stack">
						<h3 class="settings-page-section-title">Configuration (read-only)</h3>
						<div class="panel stack">
							{#each systemGroup.fields as f (f.key)}
								<ConfigSchemaField field={f} value={(settings.config as Record<string, unknown>)?.[f.key] ?? settings.infra?.[f.key]} />
							{/each}
						</div>
					</section>
				{/if}
			</div>

			<!-- Diagnostics (moved here from the standalone Diagnostics tab) -->
			<section class="mt-6">
				<DiagnosticsSection />
			</section>
		{/if}

		<!-- Appearance Tab -->
		{#if activeTab === 'interface'}
			<InterfaceSettings />
		{/if}

		{#if activeTab === 'themes'}
			<h2 class="settings-page-section-title mb-4">Themes</h2>
			<section class="stack stack-lg">
				<!-- Feedback toast -->
				{#if themeFeedback}
					<div class="alert {themeFeedback.type === 'success' ? 'alert-success' : 'alert-danger'}">
						{themeFeedback.message}
					</div>
				{/if}

				<!-- Built-in Themes -->
				<div class="panel settings-page-panel-wide">
					<h3 class="settings-page-panel-title">Color Scheme</h3>
					<p class="settings-page-description settings-page-panel-hint">Choose an accent color for buttons, links, and highlights throughout the UI.</p>
					<div class="flex flex-wrap gap-3">
						{#each $allSchemes.filter(s => s.builtin !== false) as scheme}
							<button
								type="button"
								onclick={() => ($colorScheme = scheme.id)}
								class="scheme-swatch-btn"
								data-selected={$colorScheme === scheme.id}
							>
								<span class="scheme-swatch" style:--swatch={scheme.swatch}></span>
								<span class="scheme-swatch-label">{scheme.label}</span>
								{#if scheme.description}
									<span class="scheme-swatch-tooltip">{scheme.description}</span>
								{/if}
							</button>
						{/each}
					</div>
				</div>

				<!-- User Themes -->
				{#if $allSchemes.filter(s => s.builtin === false).length > 0}
					<div class="panel settings-page-panel-wide">
						<h3 class="settings-page-panel-title">User Themes</h3>
						<p class="settings-page-description settings-page-panel-hint">Custom themes loaded from your themes directory.</p>
						<div class="flex flex-wrap gap-3">
							{#each $allSchemes.filter(s => s.builtin === false) as scheme}
								<div class="relative">
									<button
										type="button"
										onclick={() => ($colorScheme = scheme.id)}
										class="scheme-swatch-btn"
										data-selected={$colorScheme === scheme.id}
									>
										<span class="scheme-swatch" style:--swatch={scheme.swatch}></span>
										<span class="scheme-swatch-label">{scheme.label}</span>
										{#if scheme.author}
											<span class="scheme-swatch-author">by {scheme.author}</span>
										{/if}
									</button>
									<div class="absolute -right-1 -top-1 flex gap-0.5">
										<button
											type="button"
											onclick={() => handleThemeDelete(scheme.id, scheme.label)}
											class="btn btn-icon scheme-swatch-delete"
											title="Delete"
										>
											<Glyph name="x" class="h-3 w-3" />
										</button>
									</div>
								</div>
							{/each}
						</div>
						{#if themeFeedback}
							<p class="mt-3 settings-page-feedback" data-error={themeFeedback.type !== 'success'}>
								{themeFeedback.message}
							</p>
						{/if}
					</div>
				{/if}

				<!-- Dark Mode -->
				<div class="panel settings-page-panel-wide">
					<div class="flex items-center justify-between">
						<div>
							<h3 class="settings-page-panel-title settings-page-panel-title-flush">Dark Mode</h3>
							{#if $schemeLocksMode}
								<p class="settings-page-description">Locked by theme</p>
							{:else}
								<p class="settings-page-description">Toggle between light and dark mode.</p>
							{/if}
						</div>
						{#if !$schemeLocksMode}
							<div class="flex items-center gap-2">
								<button
									type="button"
									onclick={toggleTheme}
									role="switch"
									aria-checked={$theme === 'dark'}
									aria-label="Dark mode"
									class="toggle toggle-lg"
								>
									<span class="toggle-thumb"></span>
								</button>
								<span class="settings-page-toggle-label" data-on={$theme === 'dark'}>
									{$theme === 'dark' ? 'On' : 'Off'}
								</span>
							</div>
						{/if}
					</div>
				</div>

				<!-- Image Cache -->
				<div class="panel settings-page-panel-wide">
					<div class="flex items-center justify-between">
						<div>
							<h3 class="settings-page-panel-title settings-page-panel-title-flush">Image Cache</h3>
							<p class="settings-page-description mt-1">
								{#if cacheLoading}Loading...
								{:else if cacheStats}{cacheStats.count} cached image{cacheStats.count !== 1 ? 's' : ''} ({cacheStats.size_mb} MB)
								{:else}Unable to load cache stats
								{/if}
							</p>
						</div>
						<button type="button"
							onclick={() => (cacheConfirmOpen = true)}
							disabled={cacheBusy || !cacheStats?.count}
							class="btn btn-danger btn-sm settings-page-clear-cache-btn">
							Clear Cache
						</button>
					</div>
					{#if cacheFeedback}
						<p class="mt-2 settings-page-feedback" data-error={cacheFeedback.type !== 'success'}>
							{cacheFeedback.message}
						</p>
					{/if}
				</div>

				<!-- Feature request prompt -->
				<div class="flex justify-center pt-2">
					<span class="badge settings-page-feature-request">
						<Glyph name="info" class="h-3.5 w-3.5" />
						Not seeing what you want? Submit your feature requests on GitHub.
					</span>
				</div>
			</section>
		{/if}

		{#if activeTab === 'drives'}
			<div class="mb-4 flex items-start justify-between gap-3">
				<h2 class="settings-page-section-title">Drives</h2>
				<DriveMaintenance onrescanned={() => drives.refresh()} />
			</div>
			<section class="stack stack-lg">
				{#if $driveError}
					<div class="alert alert-danger">
						{$driveError}
					</div>
				{:else}
					{#if parts.enrolled.length > 0}
						<div class="grid-2 settings-page-drive-grid">
							{#each parts.enrolled as drive (drive.id)}
								<DriveCard {drive} sessions={driveSessions} onupdate={() => drives.refresh()} globalDefaults={{
									prescan_cache_mb: Number(settings?.arm_config?.PRESCAN_CACHE_MB) || 1,
									prescan_timeout: Number(settings?.arm_config?.PRESCAN_TIMEOUT) || 300,
									prescan_retries: Number(settings?.arm_config?.PRESCAN_RETRIES) || 3,
									disc_enum_timeout: Number(settings?.arm_config?.DISC_ENUM_TIMEOUT) || 60,
								}} />
							{/each}
						</div>
					{/if}
					<DriveLifecycleLists detected={parts.detected} ignored={parts.ignored} onchanged={() => drives.refresh()} />
				{/if}

				<!-- Diagnostics -->
				<hr class="settings-page-diag-divider" />
				<div data-diag>
					<button
						onclick={() => { diagOpen = !diagOpen; }}
						aria-expanded={diagOpen}
						class="btn settings-page-diag-toggle"
					>
						<Glyph name="shield-check" />
						Udev & Drive Diagnostics
						<Glyph name="chevron-down" class="chevron ml-auto" />
					</button>

					{#if diagOpen}
						<div class="panel-section settings-page-diag-panel" transition:slide={{ duration: 200 }}>
							<div class="mb-2.5 flex items-center justify-between">
								<button
									onclick={runDiagnostic}
									disabled={diagRunning}
									data-busy={diagRunning}
									class="btn settings-page-diag-run"
								>
									<Glyph name="refresh" class="settings-page-diag-run-icon" />
									{diagRunning ? 'Running...' : 'Run Check'}
								</button>
								{#if diagLastRun}
									<span class="settings-page-diag-last-run">Last run: {diagLastRun}</span>
								{/if}
								{#if diagError}
									<span class="settings-page-diag-error">{diagError}</span>
								{/if}
							</div>

							{#if diagResult}
								{@const system = diagResult.system ?? []}
								{@const unhealthy = diagResult.drives.filter(d => !d.healthy || (d.notes.length > 0 && !(d.notes.length === 1 && d.notes[0] === 'ignored')))}
								{#if system.length > 0}
									<div class="alert alert-warning mb-2 settings-page-diag-system" data-testid="diag-system">
										{#each system as note}
											<div>{note}</div>
										{/each}
									</div>
								{/if}

								<!-- Status bar -->
								<div class="alert {unhealthy.length > 0 || system.length > 0 ? 'alert-warning' : 'alert-success'} mb-2 flex flex-wrap items-center gap-3">
									<span class="settings-page-diag-count">
										{diagResult.drives.length} drive{diagResult.drives.length !== 1 ? 's' : ''}
									</span>
									<span class="alert-title">
										{unhealthy.length > 0 || system.length > 0 ? 'Issues Found' : 'All OK'}
									</span>
								</div>

								<!-- Every drive, healthy or not -->
								{#each diagResult.drives as diag (diag.id)}
									{@const flagged = unhealthy.includes(diag)}
									<div data-testid="diag-drive-{diag.id}" class="settings-page-diag-drive" data-flagged={flagged}>
										<div class="flex flex-wrap items-center gap-x-2 gap-y-1 settings-page-diag-drive-row">
											<code class="mono settings-page-diag-drive-path">{diag.device_path}</code>
											<span class="badge badge-sm">{diag.lifecycle}</span>
											<span data-warn={!diag.present}>{diag.present ? 'connected' : 'not connected'}</span>
											{#if diag.container}<span>container: {diag.container}</span>{/if}
											{#if diag.status}<span>ripper: {diag.status}</span>{/if}
											{#if diag.media_status}<span>media: {diag.media_status.replace('_', ' ')}</span>{/if}
											{#if diag.media_status_at}<span class="settings-page-diag-heartbeat">heartbeat {formatDateTime(diag.media_status_at)}</span>{/if}
											{#if !flagged}<span class="ml-auto settings-page-diag-ok">OK</span>{/if}
										</div>
										{#if diag.last_error}
											<div class="field-error mt-1">{diag.last_error}</div>
										{/if}
										{#each diag.notes as note}
											<div class="mt-1 flex items-start gap-1.5 settings-page-diag-note">
												{#if note === 'ignored'}
													<span class="settings-page-diag-ignored">ignored</span>
												{:else}
													<Glyph name="warning" class="mt-0.5 h-3 w-3 flex-shrink-0 settings-page-diag-warn-icon" />
													<span class="settings-page-diag-warn-text">{note}</span>
												{/if}
											</div>
										{/each}
										{#if diag.notes.length === 0 && !diag.healthy}
											<div class="settings-page-diag-warn-text mt-1">unhealthy</div>
										{/if}
									</div>
								{/each}
							{:else if !diagRunning}
								<p class="settings-page-diag-empty">Click "Run Check" to scan drives and udev configuration.</p>
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

<style>
	/* pb-20: extra bottom padding so the last tab's content clears the mobile
	   bottom bar / drawer trigger. */
	.settings-page { padding-bottom: 5rem; }
	.settings-page-section-title { font-size: 1.125rem; line-height: 1.75rem; font-weight: 600; color: var(--color-text); }
	/* the section-card h3s in Themes were text-base font-semibold (1rem/
	   1.5rem), distinct from .panel-title's uppercase eyebrow look. */
	.settings-page-panel-title { margin-bottom: 0.25rem; font-size: 1rem; line-height: 1.5rem; font-weight: 600; color: var(--color-text); }
	/* Dark Mode's and Image Cache's h3 had no mb-1 in the original (only
	   Color Scheme's and User Themes' did). */
	.settings-page-panel-title-flush { margin-bottom: 0; }
	/* the original Clear Cache button had no border at all
	   (text-red-600 hover:bg-red-500/10), not btn-danger's outlined look. */
	.settings-page-clear-cache-btn { border-color: transparent; }
	.settings-page-clear-cache-btn:hover { background: var(--color-danger-soft); }
	/* most "muted description under a heading" paragraphs on this page were
	   text-sm (0.875rem/1.25rem), not panel-hint's 0.75rem - panel-hint is
	   sized for a note under a form control, a visibly smaller role. */
	.settings-page-description { font-size: 0.875rem; line-height: 1.25rem; color: var(--color-text-muted); }
	.settings-page-panel-hint { margin-bottom: 1rem; margin-top: 0; }
	.settings-page-notifications-off { text-align: center; padding: 1.5rem 1rem; font-size: 0.875rem; line-height: 1.25rem; color: var(--color-text-muted); }
	.settings-page-toggle-label { font-size: 0.75rem; font-weight: 500; color: var(--color-text-faint); }
	.settings-page-toggle-label[data-on="true"] { color: var(--color-primary-text); }
	.settings-page-feedback { font-size: 0.875rem; color: var(--color-text-muted); }
	.settings-page-feedback[data-error="true"] { color: var(--color-danger); }
	/* text-xs text-gray-500 - a plain inline span in the toggle row, not
	   panel-hint's block-level note (whose own margin-top would misalign
	   it against its row siblings). */
	.settings-page-inline-hint { font-size: 0.75rem; line-height: 1rem; color: var(--color-text-muted); }
	/* the original toggle row was gap-3 (0.75rem), not field-row's 0.5rem. */
	.settings-page-notif-toggle-row { gap: 0.75rem; }

	/* .tabs' own border-bottom, inside this strip's overflow-x-auto, adds a
	   spurious 1px vertical scrollbar without overflow-y hidden; mb-2 keeps
	   the tab strip from feeling cramped against the page title above the
	   outer .stack gap. */
	.settings-page-tabs { margin-bottom: 0.5rem; overflow-y: hidden; }
	/* the Themes tab's four cards were p-6 (1.5rem) in the original, not
	   .panel's own p-4 (1rem) default. */
	.settings-page-panel-wide { padding: 1.5rem; }

	/* Color scheme swatch buttons (Themes tab): a bordered pill holding a
	   round color sample, its label, and (built-in schemes) a hover tooltip
	   or (user themes) a delete button. No block covers this shape. */
	.scheme-swatch-btn { position: relative; display: flex; flex-direction: column; align-items: center; gap: 0.375rem; border: 2px solid var(--color-border); border-radius: var(--radius-lg); padding: 0.75rem 1rem; background: none; cursor: pointer; transition: border-color var(--motion-fast) var(--ease), background-color var(--motion-fast) var(--ease); }
	.scheme-swatch-btn:hover { border-color: var(--color-border-strong); }
	.scheme-swatch-btn[data-selected="true"] { border-color: var(--color-primary); background: var(--color-primary-tint-3); }
	.scheme-swatch { display: block; width: 2rem; height: 2rem; border-radius: 9999px; background: var(--swatch); }
	.scheme-swatch-label { font-size: 0.75rem; line-height: 1rem; font-weight: 500; color: var(--color-text-secondary); }
	.scheme-swatch-author { font-size: 0.625rem; color: var(--color-text-faint); }
	.scheme-swatch-tooltip { position: absolute; top: -2rem; left: 50%; transform: translateX(-50%); white-space: nowrap; border-radius: var(--radius-sm); background: var(--color-surface-raised); padding: 0.25rem 0.5rem; font-size: 0.625rem; color: var(--color-text); opacity: 0; pointer-events: none; transition: opacity var(--motion-fast) var(--ease); box-shadow: var(--shadow-1); }
	.scheme-swatch-btn:hover .scheme-swatch-tooltip { opacity: 1; }
	.scheme-swatch-delete { position: absolute; }

	/* Drive cards grid: 2 columns at md, matching the original's md:2/xl:3
	   step (grid-2's own responsive breaks at sm, so xl needs its own rule). */
	.settings-page-drive-grid { grid-template-columns: 1fr; }
	@media (min-width: 768px) { .settings-page-drive-grid { grid-template-columns: repeat(2, 1fr); } }
	@media (min-width: 1280px) { .settings-page-drive-grid { grid-template-columns: repeat(3, 1fr); } }

	.settings-page-feature-request { gap: 0.375rem; background: var(--color-primary-tint-2); padding: 0.5rem 1rem; }

	/* Udev & Drive Diagnostics disclosure: a full-width outlined toggle
	   button over a collapsible detail panel, none of it matching .panel's
	   metrics (this reuses .panel-section's tint but at its own padding). */
	/* the original `<hr class="my-2">` sat in a `space-y-6` (margin) stack:
	   Tailwind v4's zero-specificity space-y rule lost to my-2, so the hr's
	   own 0.5rem margin-top collapsed into the panel's 1.5rem margin-bottom
	   (24px above) and its 0.5rem margin-bottom stood alone (8px below,
	   the diag div being the last child and so getting no space-y margin).
	   .stack-lg's flex gap never collapses, so cancel 1rem below the hr to
	   reproduce the original 24px/8px split. */
	.settings-page-diag-divider { margin: 0 0 -1rem; border: 0; border-top: 1px solid var(--color-text); opacity: 0.2; }
	/* the original border was border-primary/15 (--color-border), lighter
	   than .btn's default border-primary-strong. */
	/* px-3.5 py-2.5 (0.875rem/0.625rem), not .btn's own 1rem/0.5rem - 4px
	   taller than .btn's default, and the toggle sets the height of
	   everything below it on the Drives tab. */
	.settings-page-diag-toggle { width: 100%; justify-content: flex-start; gap: 0.5rem; padding: 0.625rem 0.875rem; border-color: var(--color-border); background: var(--color-primary-tint-1); }
	/* the original chevron flipped a full 180deg (open = pointing up);
	   .btn's shared .chevron rule only rotates 90deg, tuned for a
	   right-pointing chevron that turns to point down. */
	.settings-page-diag-toggle[aria-expanded="true"] :global(.chevron) { transform: rotate(180deg); } /* :global: .chevron is rendered by the child Glyph component, outside this component's own scoped template */
	.settings-page-diag-panel { margin-top: 0.625rem; padding: 0.75rem; }
	/* the original button was a tinted fill (bg-primary/15, no border), not
	   .btn's default outlined look. */
	.settings-page-diag-run { padding: 0.375rem 0.875rem; border-color: transparent; background: var(--color-primary-tint-3); color: var(--color-primary-text); }
	.settings-page-diag-run:hover { background: color-mix(in srgb, var(--color-primary) 25%, transparent); }
	button[data-busy="true"] :global(.settings-page-diag-run-icon) { animation: settings-page-spin 1s linear infinite; } /* :global: class forwarded onto Glyph's internal <svg>, outside this component's own template */
	@keyframes settings-page-spin { to { transform: rotate(360deg); } }
	.settings-page-diag-last-run { font-size: 0.625rem; color: var(--color-text-faint); }
	/* the original diagError span was text-sm (0.875rem/1.25rem), not
	   field-error's 0.75rem. */
	.settings-page-diag-error { font-size: 0.875rem; line-height: 1.25rem; color: var(--color-danger); }
	.settings-page-diag-system { font-size: 0.75rem; padding: 0.625rem; }
	.settings-page-diag-count { font-size: 0.75rem; color: var(--color-text-muted); }
	.settings-page-diag-drive { margin-bottom: 0.375rem; border: 1px solid var(--color-border); border-radius: var(--radius-lg); padding: 0.625rem; }
	.settings-page-diag-drive[data-flagged="true"] { border-color: color-mix(in srgb, var(--color-warning) 30%, transparent); background: var(--color-warning-soft); }
	.settings-page-diag-drive-row { font-size: 0.75rem; color: var(--color-text-secondary); }
	.settings-page-diag-drive-path { font-weight: 500; color: var(--color-text); }
	.settings-page-diag-drive-row [data-warn="true"] { color: var(--color-on-warning-soft); }
	.settings-page-diag-heartbeat { color: var(--color-text-faint); }
	.settings-page-diag-ok { font-weight: 500; color: var(--color-success); }
	.settings-page-diag-note { font-size: 0.75rem; }
	.settings-page-diag-ignored { color: var(--color-text-faint); }
	/* :global: forwarded onto Glyph's internal <svg>, as above. */
	:global(.settings-page-diag-warn-icon) { color: var(--color-warning); }
	.settings-page-diag-warn-text { color: var(--color-on-warning-soft); }
	.settings-page-diag-empty { text-align: center; font-size: 0.75rem; color: var(--color-text-faint); }

	/* :global below: applied/removed via classList in the $effect above (deep
	   link #<tab>/<field>), not a template-driven state attribute this
	   component's own selectors could reach. */
	:global(.settings-field-highlight) /* see comment above */ { box-shadow: 0 0 0 2px var(--color-page), 0 0 0 4px var(--color-primary); }
</style>
