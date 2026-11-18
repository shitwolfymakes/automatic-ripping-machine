<script lang="ts">
	import type { DriveView as Drive } from '$lib/types/api.gen';
	import type { SettingsData } from '$lib/api/settings';
	import type { DriveSessionOptions } from '$lib/stores/drive-session-options.svelte';
	import type { DriveDiagnostics } from '$lib/stores/drive-diagnostics.svelte';
	import { partitionDrives } from '$lib/drives/drives';
	import DriveCard from '$lib/components/drives/DriveCard.svelte';
	import DriveMaintenance from '$lib/components/drives/DriveMaintenance.svelte';
	import DriveLifecycleLists from '$lib/components/drives/DriveLifecycleLists.svelte';
	import DriveDiagnosticsPanel from '$lib/components/settings/DriveDiagnosticsPanel.svelte';

	interface Props {
		drives: Drive[];
		error: string | null;
		onrefresh: () => void;
		options: DriveSessionOptions;
		settings: SettingsData;
		diagnostics: DriveDiagnostics;
	}

	let { drives, error, onrefresh, options, settings, diagnostics }: Props = $props();

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
							globalDefaults={{
								prescan_cache_mb: Number(settings?.arm_config?.PRESCAN_CACHE_MB) || 1,
								prescan_timeout: Number(settings?.arm_config?.PRESCAN_TIMEOUT) || 300,
								prescan_retries: Number(settings?.arm_config?.PRESCAN_RETRIES) || 3,
								disc_enum_timeout: Number(settings?.arm_config?.DISC_ENUM_TIMEOUT) || 60
							}}
						/>
					{/each}
				</div>
			{/if}
			<DriveLifecycleLists detected={parts.detected} ignored={parts.ignored} onchanged={() => onrefresh()} />
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

	/* Drive cards grid: 2 columns at md, matching the original's md:2/xl:3
	   step (grid-2's own responsive breaks at sm, so xl needs its own rule). */
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
