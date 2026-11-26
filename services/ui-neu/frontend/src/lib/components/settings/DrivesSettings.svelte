<script lang="ts">
	import type { DriveView as Drive, SettingsGroup } from '$lib/types/api.gen';
	import type { SettingsData } from '$lib/api/settings';
	import type { DriveSessionOptions } from '$lib/stores/drive-session-options.svelte';
	import type { DriveDiagnostics } from '$lib/stores/drive-diagnostics.svelte';
	import { partitionDrives } from '$lib/drives/drives';
	import DriveCard from '$lib/components/drives/DriveCard.svelte';
	import DriveMaintenance from '$lib/components/drives/DriveMaintenance.svelte';
	import DriveLifecycleLists from '$lib/components/drives/DriveLifecycleLists.svelte';
	import DriveDiagnosticsPanel from '$lib/components/settings/DriveDiagnosticsPanel.svelte';
	import SchemaConfigForm from '$lib/components/settings/SchemaConfigForm.svelte';

	interface Props {
		drives: Drive[];
		error: string | null;
		onrefresh: () => void;
		options: DriveSessionOptions;
		settings: SettingsData;
		diagnostics: DriveDiagnostics;
		/** The Drives schema group (drive scanner tunables); absent until the schema loads. */
		group?: SettingsGroup;
		onsaved?: (payload: Record<string, unknown>) => void;
	}

	let { drives, error, onrefresh, options, settings, diagnostics, group, onsaved }: Props = $props();

	let parts = $derived(partitionDrives(drives));
</script>

<div class="stack stack-lg" data-page-section>
	<div class="mb-4 flex items-start justify-between gap-3">
		<h2 class="settings-page-section-title" data-page-section-title>Drives</h2>
		<DriveMaintenance onrescanned={() => onrefresh()} />
	</div>
	<section class="stack stack-lg">
		{#if error}
			<div class="alert alert-danger">
				{error}
			</div>
		{:else}
			{#if parts.enrolled.length > 0}
				<div class="grid-2 settings-page-drive-grid">
					{#each parts.enrolled as drive (drive.id)}
						<DriveCard
							{drive}
							sessions={options.sessions}
							transcodePresets={options.transcodePresets}
							globalAutoRip={settings?.config?.auto_rip_on_insert !== false}
							onupdate={() => onrefresh()}
							globalDefaults={{ prescan_timeout: settings?.config?.default_scan_timeout_seconds }}
						/>
					{/each}
				</div>
			{/if}
			<DriveLifecycleLists detected={parts.detected} ignored={parts.ignored} onchanged={() => onrefresh()} />
		{/if}

		{#if group}
			<section class="panel stack" data-testid="drive-scanning">
				<h3 class="settings-page-subsection-title">Scanning</h3>
				<SchemaConfigForm bare {group} config={settings?.config ?? {}} {onsaved} />
			</section>
		{/if}

		<!-- Diagnostics -->
		<DriveDiagnosticsPanel {diagnostics} />
	</section>
</div>

<style>
	.settings-page-section-title {
		font-size: 1.125rem;
		line-height: 1.75rem;
		font-weight: 600;
		color: var(--color-text);
	}

	.settings-page-subsection-title {
		font-size: 1rem;
		font-weight: 600;
		color: var(--color-text);
	}

	/* Drive cards grid: 2 columns at md, stepping to 3 at xl (grid-2's own responsive breaks at sm, so xl needs its own rule). */
	.settings-page-drive-grid {
		grid-template-columns: 1fr;
	}
	@media (min-width: 768px) {
		.settings-page-drive-grid {
			grid-template-columns: repeat(2, 1fr);
		}
	}
	@media (min-width: 1280px) {
		.settings-page-drive-grid {
			grid-template-columns: repeat(3, 1fr);
		}
	}
</style>
