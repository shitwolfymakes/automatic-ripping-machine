<script lang="ts">
	import type { DriveView as Drive } from '$lib/types/api.gen';
	import { onMount } from 'svelte';

	let drives = $state<Drive[]>([]);
	let loading = $state(true);
	let error = $state<string | null>(null);

	async function loadDrives() {
		loading = true;
		error = null;
		try {
			const resp = await fetch('/api/drives');
			if (resp.ok) {
				drives = await resp.json();
			} else {
				error = 'Failed to load drives';
			}
		} catch {
			error = 'Could not reach the server';
		} finally {
			loading = false;
		}
	}

	onMount(() => { loadDrives(); });
</script>

<div class="stack stack-lg">
	<div class="drive-scan-step-header">
		<h2 class="drive-scan-step-title">Optical Drives</h2>
		<p class="drive-scan-step-subtitle">
			ARM detects your optical drives automatically.
		</p>
	</div>

	{#if loading}
		<div class="drive-scan-step-status">Scanning for drives...</div>
	{:else if error}
		<div class="alert alert-danger alert-lg">
			{error}
		</div>
	{:else if drives.length === 0}
		<div class="panel drive-scan-step-empty">
			<svg class="mx-auto h-12 w-12 drive-scan-step-empty-icon" fill="none" stroke="currentColor" viewBox="0 0 24 24" stroke-width="1.5">
				<circle cx="12" cy="12" r="10" />
				<circle cx="12" cy="12" r="3" />
			</svg>
			<p class="drive-scan-step-empty-title">
				No optical drives detected
			</p>
			<p class="drive-scan-step-empty-hint">
				ARM will detect drives when they become available. This is normal in VM or NAS environments.
			</p>
		</div>
	{:else}
		<div class="stack stack-sm">
			{#each drives as drive}
				<div class="panel">
					<div class="flex items-center justify-between">
						<h3 class="drive-scan-step-drive-name">
							{drive.display_name || drive.device_path || `Drive ${drive.id}`}
						</h3>
					</div>
					<p class="drive-scan-step-drive-meta">
						<span class="mono">{drive.device_path}</span>
						{#if drive.hostname} | {drive.hostname}{/if}
					</p>
				</div>
			{/each}
		</div>
	{/if}

	<div class="drive-scan-step-header">
		<button
			type="button"
			onclick={loadDrives}
			disabled={loading}
			class="btn drive-scan-step-scan-btn"
		>
			{loading ? 'Scanning...' : 'Scan Again'}
		</button>
	</div>
</div>

<style>
	.drive-scan-step-header { text-align: center; }
	.drive-scan-step-title { font-size: 1.5rem; line-height: 2rem; font-weight: 700; color: var(--color-text); }
	.drive-scan-step-subtitle { margin-top: 0.5rem; color: var(--color-text-muted); }
	.drive-scan-step-status { padding: 2rem 0; text-align: center; color: var(--color-text-faint); }
	.drive-scan-step-empty { text-align: center; }
	.drive-scan-step-empty-icon { color: var(--color-text-faint); }
	.drive-scan-step-empty-title { margin-top: 0.75rem; font-size: 0.875rem; line-height: 1.25rem; font-weight: 500; color: var(--color-text-muted); }
	.drive-scan-step-empty-hint { margin-top: 0.25rem; font-size: 0.75rem; line-height: 1rem; color: var(--color-text-faint); }
	.drive-scan-step-drive-name { font-weight: 600; color: var(--color-text); }
	.drive-scan-step-drive-meta { margin-top: 0.25rem; font-size: 0.875rem; line-height: 1.25rem; color: var(--color-text-muted); }
	/* original was a tinted-fill button (bg-primary/15, no border) - .btn's
	   own outlined default doesn't reproduce that, so the fill/border are
	   restated; padding/font-size match .btn's own defaults already */
	.drive-scan-step-scan-btn { border: 0; background: var(--color-primary-tint-3); color: var(--color-primary-text); }
	.drive-scan-step-scan-btn:hover { background: color-mix(in srgb, var(--color-primary-tint-3) 70%, var(--color-primary)); }
</style>
