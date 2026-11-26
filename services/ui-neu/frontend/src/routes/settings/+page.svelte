<script lang="ts">
	import { SetupRestart } from '$lib/stores/setup-restart.svelte';
	import { onMount, setContext } from 'svelte';
	import { reveal } from '$lib/ui/transitions';
	import LoadState from '$lib/components/shared/LoadState.svelte';
	import SkeletonCard from '$lib/components/shared/SkeletonCard.svelte';
	import { LoadedSettings } from '$lib/stores/loaded-settings.svelte';
	import type { DriveView as Drive, SettingsGroup } from '$lib/types/api.gen';
	import SchemaConfigForm from '$lib/components/settings/SchemaConfigForm.svelte';
	import { SETTINGS_SCHEMA_CONTEXT } from '$lib/settings/sections';
	import {
		SCREEN_TABS,
		fieldFromHash,
		fieldTab,
		orderedConfigGroups,
		settingsTabLabel,
		tabFromHash
	} from '$lib/settings/tabs';
	import { UserThemes } from '$lib/stores/user-themes.svelte';
	import { createPollingStore } from '$lib/stores/polling';
	import { fetchDrives, rescanDrives } from '$lib/api/drives';
	import { DriveDiagnostics } from '$lib/stores/drive-diagnostics.svelte';
	import { DriveSessionOptions } from '$lib/stores/drive-session-options.svelte';
	import InterfaceSettings from '$lib/components/settings/InterfaceSettings.svelte';
	import { ImageCache } from '$lib/stores/image-cache.svelte';
	import ImageCacheCard from '$lib/components/settings/ImageCacheCard.svelte';
	import DrivesSettings from '$lib/components/settings/DrivesSettings.svelte';
	import ConfirmDialog from '$lib/components/shared/ConfirmDialog.svelte';
	import SystemSettings from '$lib/components/settings/SystemSettings.svelte';
	import { setTranscodeRuntimeEnabled } from '$lib/stores/config';
	import NotificationsSettings from '$lib/components/settings/NotificationsSettings.svelte';
	import TranscodingSettings from '$lib/components/settings/TranscodingSettings.svelte';
	import ToastHost from '$lib/components/layout/ToastHost.svelte';
	import SessionsArea from '$lib/components/sessions/SessionsArea.svelte';
	import UsersCard from '$lib/components/settings/UsersCard.svelte';
	import ThemesSettings from '$lib/components/settings/ThemesSettings.svelte';

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

	// Fetch what the opened tab shows.
	function loadTabData(tab: Tab) {
		if (tab === 'interface') imageCache.load();
		if (tab === 'drives') driveSessionOptions.load();
	}

	// Set to true while we are mutating window.location.hash ourselves,
	// so the hashchange listener can skip the work setTab already did
	// (otherwise tab clicks scroll twice — once here, once in the listener).
	let programmaticHashChange = false;

	function setTab(tab: Tab) {
		activeTab = tab;
		programmaticHashChange = true;
		window.location.hash = tab;
		loadTabData(tab);
		// Reset scroll to top when switching tabs
		document.querySelector('main')?.scrollTo(0, 0);
	}

	const setupRestart = new SetupRestart();

	onMount(() => {
		// Rescan drives to pick up hardware info (model, serial) that
		// may not have been available at container startup.
		rescanDrives()
			.catch(() => {})
			.then(() => drives.start());
		loaded.load();
		// Handle initial hash tab (trigger side effects)
		loadTabData(activeTab);
		function onHashChange() {
			if (programmaticHashChange) {
				programmaticHashChange = false;
				return;
			}
			const tab = tabFromHash(window.location.hash);
			activeTab = tab;
			pendingField = fieldFromHash(window.location.hash);
			loadTabData(tab);
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
			 tabs"> wrapper keeps the strip selectable with nav[aria-label="Settings tabs"]; it is an
			 unstyled block box.
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
				<TranscodingSettings group={transcodingGroup} config={settings.config} onsaved={onTranscodingSaved} />
			{/if}

			{#if activeTab === 'sessions'}
				<div class="space-y-6" data-page-section>
					<SessionsArea />
				</div>
			{/if}

			<!-- Notifications Tab -->
			{#if activeTab === 'notifications'}
				<NotificationsSettings
					enabled={Boolean(settings.config?.notifications_enabled)}
					ontoggle={loaded.toggleNotifications}
				/>
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
				<SystemSettings {settings} group={systemGroup} setup={setupRestart} />
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
</style>
