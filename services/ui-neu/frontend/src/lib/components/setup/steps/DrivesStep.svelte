<script lang="ts">
	import { onMount, onDestroy } from 'svelte';
	import type { DriveView, SetupView } from '$lib/types/api.gen';
	import DriveCard from '$lib/components/DriveCard.svelte';
	import DriveLifecycleLists from '$lib/components/DriveLifecycleLists.svelte';
	import DriveMaintenance from '$lib/components/DriveMaintenance.svelte';
	import CopyBlock from '$lib/components/CopyBlock.svelte';
	import Glyph from '$lib/components/Glyph.svelte';
	import { fetchDrives } from '$lib/api/drives';
	import { fetchSystemDiagnostics } from '$lib/api/system';
	import { fetchIsoLibrary } from '$lib/api/iso';
	import { createPollingStore } from '$lib/stores/polling';
	import { partitionDrives } from '$lib/utils/drives';
	import type { StepCommitResult } from '../steps';

	// Step 3, the core step: enroll the drives to rip with (setup spec §5.4).
	// The same drive components as Settings > Drives; changes save as made.
	let { view }: { view: SetupView; setBlocked?: (reason: string | null) => void } = $props();
	void view;

	const drives = createPollingStore(fetchDrives, [] as DriveView[], 3000);
	const parts = $derived(partitionDrives($drives));
	let enrollDisabledReason = $state<string | null>(null);
	let iso = $state<{ on: boolean; count: number; path: string | null } | null>(null);

	onMount(async () => {
		drives.start();
		const [diag, lib] = await Promise.allSettled([fetchSystemDiagnostics(), fetchIsoLibrary()]);
		if (diag.status === 'fulfilled') {
			const rm = diag.value.checks.find((c) => c.name === 'ripper_manager');
			if (rm && rm.status !== 'ok')
				enrollDisabledReason = "Drives can't be enrolled until the ripper service is fixed. See System check.";
		}
		iso =
			lib.status === 'fulfilled'
				? { on: true, count: lib.value.entries.filter((e) => e.kind === 'iso').length, path: lib.value.host_path }
				: { on: false, count: 0, path: null };
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
				{total} drive{total === 1 ? '' : 's'} found{parts.ignored.length ? `, ${parts.ignored.length} ignored` : ''}
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
		<section class="panel stack drives-step-iso" data-testid="drives-iso">
			<div class="drives-step-iso-head">
				<span class="drives-step-iso-title"><Glyph name="disc-3" /> Rip from image files</span>
				<span class="chip chip-sm {iso.on ? 'chip-success' : ''}">
					<Glyph name={iso.on ? 'check-circle' : 'minus-circle'} class="h-3 w-3" />
					ISO library: {iso.on ? `on, ${iso.count} image${iso.count === 1 ? '' : 's'}` : 'off'}
				</span>
			</div>
			<p class="drives-step-help">ARM can rip ISO image files with no drive at all.</p>
			{#if iso.on && iso.path}
				<p class="drives-step-help">Images are read from <code class="mono">{iso.path}</code> on the server.</p>
			{/if}
			{#if !iso.on}
				<p class="drives-step-help">To turn it on, add this line to .env:</p>
				<CopyBlock text="ARM_HOST_ISO_LIBRARY_PATH=/path/to/your/isos" />
				<p class="drives-step-help">
					Then add the mount from the docs and restart ARM. <a href="/help">Read how</a>
				</p>
			{/if}
		</section>
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
	.drives-step-iso-head {
		display: flex;
		flex-wrap: wrap;
		align-items: center;
		justify-content: space-between;
		gap: 0.5rem;
	}
	.drives-step-iso-title {
		display: inline-flex;
		align-items: center;
		gap: 0.5rem;
		font-weight: 600;
	}
</style>
