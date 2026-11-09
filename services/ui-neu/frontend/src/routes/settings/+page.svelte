<script lang="ts">
	import { goto } from '$app/navigation';
	import { restartSetup } from '$lib/api/setup';
	import { onMount, setContext } from 'svelte';
	import { reveal } from '$lib/transitions';
	import LoadState from '$lib/components/LoadState.svelte';
	import SkeletonCard from '$lib/components/SkeletonCard.svelte';
	import { LoadedSettings } from '$lib/stores/loadedSettings.svelte';
	import type { DriveView as Drive, SettingsGroup } from '$lib/types/api.gen';
	import ConfigSchemaField from '$lib/components/settings/ConfigSchemaField.svelte';
	import SchemaConfigForm from '$lib/components/settings/SchemaConfigForm.svelte';
	import { SETTINGS_SCHEMA_CONTEXT } from '$lib/utils/settings-sections';
	import {
		SCREEN_TABS,
		fieldFromHash,
		fieldTab,
		orderedConfigGroups,
		settingsTabLabel,
		tabFromHash
	} from '$lib/utils/settings-tabs';
	import { UserThemes } from '$lib/stores/userThemes.svelte';
	import { createPollingStore } from '$lib/stores/polling';
	import { fetchDrives, rescanDrives } from '$lib/api/drives';
	import { DriveDiagnostics } from '$lib/stores/driveDiagnostics.svelte';
	import { DriveSessionOptions } from '$lib/stores/driveSessionOptions.svelte';
	import InterfaceSettings from '$lib/components/settings/InterfaceSettings.svelte';
	import { ImageCache } from '$lib/stores/imageCache.svelte';
	import ImageCacheCard from '$lib/components/settings/ImageCacheCard.svelte';
	import DrivesSettings from '$lib/components/settings/DrivesSettings.svelte';
	import ConfirmDialog from '$lib/components/ConfirmDialog.svelte';
	import SystemHealth from '$lib/components/settings/SystemHealth.svelte';
	import { transcoderEnabled, setTranscodeRuntimeEnabled } from '$lib/stores/config';
	import NotificationsTab from '$lib/components/notifications/NotificationsTab.svelte';
	import Toggle from '$lib/components/notifications/Toggle.svelte';
	import ToastHost from '$lib/components/ToastHost.svelte';
	import DiagnosticsSection from '$lib/components/DiagnosticsSection.svelte';
	import SessionsArea from '$lib/components/sessions/SessionsArea.svelte';
	import UsersCard from '$lib/components/settings/UsersCard.svelte';
	import ThemesSettings from '$lib/components/settings/ThemesSettings.svelte';
	import SessionRoutesCard from '$lib/components/settings/SessionRoutesCard.svelte';
	import GpusCard from '$lib/components/settings/GpusCard.svelte';

	const loaded = new LoadedSettings();
	// A getter, not a value: the schema arrives after mount and context is set
	// once. Field widgets use it to deep-link to another tab's field.
	setContext(SETTINGS_SCHEMA_CONTEXT, () => loaded.settings?.schema?.groups);

	// --- Tab state ---
	type Tab = string;
	const configGroups = $derived(orderedConfigGroups(loaded.settings?.schema?.groups ?? []));
	// Full visible-tab list: config groups first, then screen-tabs. The
	// Transcoding tab always shows (even on a ripper-only, not-capable
	// deployment) so the locked toggle + hint below is reachable; see the
	// 'transcoding' tab body for the capable-vs-not split.
	const visibleTabs = $derived([...configGroups.map((g) => g.name), ...SCREEN_TABS]);

	// Schema groups by name, for the template tab bodies.
	function group(name: string): SettingsGroup | undefined {
		return (loaded.settings?.schema?.groups ?? []).find((g) => g.name === name);
	}
	const identificationGroup = $derived(group('Identification'));
	const keysGroup = $derived(group('Keys'));
	const rippingGroup = $derived(group('Ripping'));
	const transcodingGroup = $derived(group('Transcoding'));
	const systemGroup = $derived(group('System'));

	let activeTab = $state<Tab>(tabFromHash(window.location.hash));

	// Deep link: `#<tab>/<field key>` (e.g. the header's Key dot points at
	// #Keys/makemkv_key). The field is scrolled into view, focused and
	// briefly highlighted once its tab has rendered. The field's own schema
	// group wins over the hash's tab, so an old link (#Metadata/tmdb_api_key)
	// still lands on the tab that now holds the field.
	let pendingField = $state<string | null>(fieldFromHash(window.location.hash));

	$effect(() => {
		const key = pendingField;
		if (!key || !loaded.settings) return;
		const home = fieldTab(loaded.settings?.schema?.groups, key, visibleTabs);
		if (home && home !== activeTab) {
			activeTab = home;
			return; // re-runs once the field's tab has rendered
		}
		const el = document.getElementById(`setting-${key}`);
		// One shot: a field that never renders must not keep pulling later tab
		// clicks back to its tab.
		pendingField = null;
		if (!el) return;
		el.scrollIntoView({ block: 'center' });
		el.querySelector<HTMLElement>('input, select, textarea')?.focus({ preventScroll: true });
		el.classList.add('settings-field-highlight');
		setTimeout(() => el.classList.remove('settings-field-highlight'), 1600);
	});

	// --- Drives polling store ---
	const drives = createPollingStore(fetchDrives, [] as Drive[], 10000);
	const driveError = drives.error;

	const driveSessionOptions = new DriveSessionOptions();

	// --- Drive diagnostics ---
	const driveDiagnostics = new DriveDiagnostics();

	// --- Theme management ---
	const userThemes = new UserThemes();

	// --- Image cache state ---
	const imageCache = new ImageCache();

	// Set to true while we are mutating window.location.hash ourselves,
	// so the hashchange listener can skip the work setTab already did
	// (otherwise tab clicks scroll twice — once here, once in the listener).
	let programmaticHashChange = false;

	function setTab(tab: Tab) {
		activeTab = tab;
		programmaticHashChange = true;
		window.location.hash = tab;
		if (tab === 'interface') imageCache.load();
		if (tab === 'drives') driveSessionOptions.load();
		// Reset scroll to top when switching tabs
		document.querySelector('main')?.scrollTo(0, 0);
	}

	let restartingSetup = $state(false);
	async function runSetupAgain() {
		restartingSetup = true;
		try {
			await restartSetup();
			goto('/setup/system');
		} finally {
			restartingSetup = false;
		}
	}

	onMount(() => {
		// Rescan drives to pick up hardware info (model, serial) that
		// may not have been available at container startup.
		rescanDrives()
			.catch(() => {})
			.then(() => drives.start());
		loaded.load();
		// Handle initial hash tab (trigger side effects)
		if (activeTab === 'interface') imageCache.load();
		if (activeTab === 'drives') driveSessionOptions.load();
		function onHashChange() {
			if (programmaticHashChange) {
				programmaticHashChange = false;
				return;
			}
			const tab = tabFromHash(window.location.hash);
			activeTab = tab;
			pendingField = fieldFromHash(window.location.hash);
			if (tab === 'interface') imageCache.load();
			if (tab === 'drives') driveSessionOptions.load();
			// Reset scroll to top when switching tabs
			document.querySelector('main')?.scrollTo(0, 0);
		}
		window.addEventListener('hashchange', onHashChange);
		return () => {
			drives.stop();
			window.removeEventListener('hashchange', onHashChange);
		};
	});

	// Keep the app-wide runtime toggle in step with a Settings save so an SPA
	// navigation to /transcoder (banner) or an apply dialog (passthrough-only
	// filter) reflects the new value without a reload. The saved values are
	// also folded back into `settings.config`: SchemaConfigForm only sends
	// fields that differ from its `config` prop, so without this a
	// disable-then-re-enable in one visit would diff against the stale
	// original value and never send the re-enable.
	function onTranscodingSaved(payload: Record<string, unknown>) {
		loaded.foldSaved(payload);
		if ('transcode_enabled' in payload) {
			setTranscodeRuntimeEnabled(Boolean(payload.transcode_enabled));
		}
	}
</script>

<svelte:head>
	<title>ARM - Settings</title>
</svelte:head>

<div class="stack stack-lg settings-page">
	<h1 class="page-title">Settings</h1>

	<LoadState data={loaded.settings} loading={loaded.loading} error={loaded.error}>
		{#snippet loadingSlot()}
			<div class="space-y-4">
				<SkeletonCard lines={5} />
				<SkeletonCard lines={4} />
			</div>
		{/snippet}
		{#snippet ready(_)}
			{@const settings = _}
			<!-- Tab Bar -->
			<!-- settings-page-tabs adds breathing room below the tab strip (mb-2) -
			 tabs feel cramped against headings otherwise. -->
			<!-- role="tablist" sits on an inner <div>, not the <nav> itself: a
			 <nav> is a non-interactive landmark and cannot carry the
			 interactive tablist role (svelte a11y
			 a11y_no_noninteractive_element_to_interactive_role). This is the
			 same shape SessionsArea.svelte uses. The <nav aria-label="Settings
			 tabs"> wrapper is kept because the parity harness selects the strip
			 with nav[aria-label="Settings tabs"]; it is an unstyled block box,
			 so the inner div reproduces the previous nav's own box exactly.
			 data-settings-tabs is the published hook schemes style it by. -->
			<nav aria-label="Settings tabs" data-settings-tabs>
				<div class="tabs settings-page-tabs" role="tablist">
					{#each visibleTabs as tab (tab)}
						<button
							type="button"
							role="tab"
							onclick={() => setTab(tab)}
							class="tabs-tab"
							aria-selected={activeTab === tab}>{settingsTabLabel(tab)}</button
						>
					{/each}
				</div>
			</nav>

			<!-- Identification, Keys and Ripping config tabs (schema-driven). All
			 three stay mounted and the inactive ones are hidden, so a chip's deep
			 link to a key on another tab (and the way back) keeps every unsaved
			 edit. Each folds its save into settings.config for the others.
			 Every tab's content sits in one data-page-section box (the published
			 hook a scheme frames a page region by), headed by its
			 data-page-section-title heading. -->
			{#each [identificationGroup, keysGroup, rippingGroup].filter((g) => g !== undefined) as g (g.name)}
				<div hidden={activeTab !== g.name} data-page-section>
					<SchemaConfigForm group={g} config={settings.config} onsaved={loaded.foldSaved} />
				</div>
			{/each}

			<!-- Transcoding Tab: schema-driven (transcode_enabled + auto_transcode_on_idle,
			 GPU inventory) when this deployment can run transcode containers.
			 On a ripper-only deployment (not capable), only the disabled
			 transcode_enabled toggle + a hint shows - GpusCard and the
			 encode-only fields (auto_transcode_on_idle, max_parallel_transcodes)
			 stay hidden. -->
			{#if activeTab === 'transcoding'}
				<div data-page-section>
					{#if $transcoderEnabled && transcodingGroup}
						<SchemaConfigForm group={transcodingGroup} config={settings.config} onsaved={onTranscodingSaved}>
							{#snippet beforeSections()}
								<GpusCard />
							{/snippet}
						</SchemaConfigForm>
					{:else}
						<div class="stack" id="setting-transcode_enabled" data-testid="setting-transcode_enabled">
							<label class="field field-row settings-page-notif-toggle-row">
								<!-- Always rendered off: on a ripper-only box the backend column
								 still defaults to true, but it has no effect without capability. -->
								<Toggle checked={false} label="Enable transcoding" disabled />
								<span class="field-label">Enable transcoding</span>
							</label>
							<p class="field-help">This deployment is ripper-only; transcoding cannot be enabled here.</p>
						</div>
					{/if}
				</div>
			{/if}

			{#if activeTab === 'sessions'}
				<div class="space-y-6" data-page-section>
					<SessionsArea />
					<SessionRoutesCard />
				</div>
			{/if}

			<!-- Notifications Tab -->
			{#if activeTab === 'notifications'}
				<div class="stack" data-page-section>
					<div>
						<h2 class="settings-page-section-title" data-page-section-title>Notifications</h2>
						<p class="settings-page-description">
							Manage notification channels - Discord, Slack, webhooks, scripts, and more.
						</p>
					</div>
					<label class="field field-row settings-page-notif-toggle-row">
						<Toggle
							checked={Boolean(settings.config?.notifications_enabled)}
							label="Enable notifications"
							onchange={loaded.toggleNotifications}
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
				<div in:reveal class="stack stack-lg" data-page-section>
					<h2 class="settings-page-section-title" data-page-section-title>Users</h2>
					<UsersCard />
				</div>
			{/if}

			<!-- System Info Tab -->
			{#if activeTab === 'system'}
				<div class="stack stack-lg" data-page-section>
					<div class="stack stack-lg">
						<h2 class="settings-page-section-title" data-page-section-title>System</h2>

						<!-- Health check (API keys + path permissions) -->
						<!-- First-run walkthrough re-entry (setup spec §5.11) -->
						<section class="panel settings-page-setup-again" data-testid="run-setup-again">
							<div>
								<h3 class="settings-page-section-title">Setup walkthrough</h3>
								<p class="settings-page-setup-again-help">
									Walk through drives, keys and defaults again. Your current values are kept.
								</p>
							</div>
							<button type="button" class="btn" onclick={runSetupAgain} disabled={restartingSetup}>
								{restartingSetup ? 'Opening...' : 'Run setup again'}
							</button>
						</section>

						<SystemHealth grouped />

						<!-- Read-only infra configuration (schema-driven) -->
						{#if systemGroup}
							<section class="stack">
								<h3 class="settings-page-section-title">Configuration (read-only)</h3>
								<div class="panel stack">
									{#each systemGroup.fields as f (f.key)}
										<ConfigSchemaField
											field={f}
											value={(settings.config as Record<string, unknown>)?.[f.key] ?? settings.infra?.[f.key]}
										/>
									{/each}
								</div>
							</section>
						{/if}
					</div>

					<!-- Diagnostics (moved here from the standalone Diagnostics tab) -->
					<section class="mt-6">
						<DiagnosticsSection />
					</section>
				</div>
			{/if}

			<!-- Appearance Tab -->
			{#if activeTab === 'interface'}
				<div class="stack stack-lg" data-page-section>
					<InterfaceSettings />

					<!-- Image Cache -->
					<ImageCacheCard cache={imageCache} />
				</div>
			{/if}

			{#if activeTab === 'themes'}
				<ThemesSettings themes={userThemes} />
			{/if}

			{#if activeTab === 'drives'}
				<DrivesSettings
					drives={$drives}
					error={$driveError}
					onrefresh={() => drives.refresh()}
					options={driveSessionOptions}
					{settings}
					diagnostics={driveDiagnostics}
				/>
			{/if}
		{/snippet}
	</LoadState>
</div>

<ConfirmDialog
	open={imageCache.confirmOpen}
	title="Clear Image Cache"
	message="Delete all cached poster images? They will be re-fetched on next view."
	confirmLabel="Clear"
	variant="danger"
	onconfirm={imageCache.clear}
	oncancel={() => (imageCache.confirmOpen = false)}
/>

<ToastHost />

<style>
	/* pb-20: extra bottom padding so the last tab's content clears the mobile
	   bottom bar / drawer trigger. */
	.settings-page {
		padding-bottom: 5rem;
	}
	.settings-page-section-title {
		font-size: 1.125rem;
		line-height: 1.75rem;
		font-weight: 600;
		color: var(--color-text);
	}
	/* most "muted description under a heading" paragraphs on this page were
	   text-sm (0.875rem/1.25rem), not panel-hint's 0.75rem - panel-hint is
	   sized for a note under a form control, a visibly smaller role. */
	.settings-page-description {
		font-size: 0.875rem;
		line-height: 1.25rem;
		color: var(--color-text-muted);
	}
	.settings-page-notifications-off {
		text-align: center;
		padding: 1.5rem 1rem;
		font-size: 0.875rem;
		line-height: 1.25rem;
		color: var(--color-text-muted);
	}
	/* text-xs text-gray-500 - a plain inline span in the toggle row, not
	   panel-hint's block-level note (whose own margin-top would misalign
	   it against its row siblings). */
	.settings-page-inline-hint {
		font-size: 0.75rem;
		line-height: 1rem;
		color: var(--color-text-muted);
	}
	/* the original toggle row was gap-3 (0.75rem), not field-row's 0.5rem. */
	.settings-page-notif-toggle-row {
		gap: 0.75rem;
	}

	/* mb-2 keeps the tab strip from feeling cramped against the page title
	   above the outer .stack gap. */
	.settings-page-tabs {
		margin-bottom: 0.5rem;
	}

	/* :global below: applied/removed via classList in the $effect above (deep
	   link #<tab>/<field>), not a template-driven state attribute this
	   component's own selectors could reach. */
	:global(.settings-field-highlight) /* see comment above */ {
		box-shadow:
			0 0 0 2px var(--color-page),
			0 0 0 4px var(--color-primary);
	}
	.settings-page-setup-again {
		display: flex;
		flex-wrap: wrap;
		align-items: center;
		justify-content: space-between;
		gap: 0.75rem;
		padding: 1.25rem;
	}
	.settings-page-setup-again-help {
		font-size: 0.875rem;
		color: var(--color-text-muted);
	}
</style>
