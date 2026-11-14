<script lang="ts">
	import { plural } from '$lib/utils/plural';
	import { onMount, onDestroy } from 'svelte';
	import type { DriveView, SetupView } from '$lib/types/api.gen';
	import DriveCard from '$lib/components/drives/DriveCard.svelte';
	import DriveLifecycleLists from '$lib/components/drives/DriveLifecycleLists.svelte';
	import DriveMaintenance from '$lib/components/drives/DriveMaintenance.svelte';
	import IsoLibraryCard from '$lib/components/setup/IsoLibraryCard.svelte';
	import { fetchDrives } from '$lib/api/drives';
	import { fetchSystemDiagnostics } from '$lib/api/system';
	import { fetchIsoLibrary } from '$lib/api/iso';
	import { createPollingStore } from '$lib/stores/polling';
	import { partitionDrives } from '$lib/drives/drives';
	import { enrollBlockReason, isoStatus, type IsoStatus } from '$lib/drives/setup-drives';
	import type { StepCommitResult } from '../../../setup/steps';

	// Step 3, the core step: enroll the drives to rip with (setup spec §5.4).
	// The same drive components as Settings > Drives; changes save as made.
	let { view }: { view: SetupView; setBlocked?: (reason: string | null) => void } = $props();
	void view;

	const drives = createPollingStore(fetchDrives, [] as DriveView[], 3000);
	const parts = $derived(partitionDrives($drives));
	let enrollDisabledReason = $state<string | null>(null);
	let iso = $state<IsoStatus | null>(null);

	onMount(async () => {
		drives.start();
		const [diag, lib] = await Promise.allSettled([fetchSystemDiagnostics(), fetchIsoLibrary()]);
		if (diag.status === 'fulfilled') enrollDisabledReason = enrollBlockReason(diag.value);
		iso = isoStatus(lib.status === 'fulfilled' ? lib.value : null);
	});
	onDestroy(() => drives.stop());

	const total = $derived(parts.enrolled.length + parts.detected.length);

	export async function commit(): Promise<StepCommitResult> {
		const ready = parts.enrolled.some((d) => d.status === 'online');
		return ready || iso?.on ? 'done' : 'attention';
	}
</script>

<div class="stack stack-lg">
	<div class="drives-step-head">
		<div>
			<p class="drives-step-count">
				{total}
				{plural(total, 'drive')} found{parts.ignored.length ? `, ${parts.ignored.length} ignored` : ''}
			</p>
			<p class="drives-step-help">ARM also rescans every 30 seconds. New drives appear here on their own.</p>
		</div>
		<DriveMaintenance onrescanned={() => drives.refresh()} />
	</div>

	{#if enrollDisabledReason}
		<div class="alert alert-warning">
			{enrollDisabledReason} <a href="/setup/system">Open System check</a>
		</div>
	{/if}

	{#each parts.enrolled as drive (drive.id)}
		<DriveCard {drive} variant="essentials" onupdate={() => drives.refresh()} />
	{/each}

	{#if total === 0 && parts.ignored.length === 0}
		<section class="panel stack" data-testid="drives-empty">
			<h2 class="drives-step-title">No drives found</h2>
			<ol class="drives-step-steps">
				<li>Plug in the drive and wait 30 seconds.</li>
				<li>Check that the drives are mounted into the backend (for example /dev/sr0).</li>
				<li>After setup, run the drive diagnostics in Settings, Drives.</li>
			</ol>
		</section>
	{:else}
		<DriveLifecycleLists
			detected={parts.detected}
			ignored={parts.ignored}
			onchanged={() => drives.refresh()}
			{enrollDisabledReason}
		/>
	{/if}

	{#if iso}
		<IsoLibraryCard {iso} />
	{/if}

	<p class="drives-step-help">More drive options are in Settings, Drives once setup is finished.</p>
</div>

<style>
	.drives-step-head {
		display: flex;
		flex-wrap: wrap;
		align-items: flex-start;
		justify-content: space-between;
		gap: 0.75rem;
	}
	.drives-step-count {
		font-weight: 600;
	}
	.drives-step-help {
		font-size: 0.875rem;
		color: var(--color-text-muted);
	}
	.drives-step-title {
		font-size: 1.0625rem;
		font-weight: 600;
	}
	.drives-step-steps {
		display: grid;
		gap: 0.375rem;
		margin: 0;
		padding-left: 1.25rem;
		font-size: 0.875rem;
	}
</style>
