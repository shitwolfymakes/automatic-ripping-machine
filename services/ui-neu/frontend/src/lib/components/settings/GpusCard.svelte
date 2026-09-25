<!-- Settings > GPUs: the DB-authoritative transcode GPU inventory (G-30).
     Rows are seeded from the host probe (ARM_GPUS) only while the table is
     empty; after that this card is how operators manage devices. Disable
     keeps a device listed but the dispatcher never claims it; delete needs
     confirmation and is refused by the server (409) while a running
     transcode holds the claim. -->
<script lang="ts">
	import { onMount } from 'svelte';
	import type { GpuView } from '$lib/types/api.gen';
	import { fetchGpus, updateGpu, deleteGpu } from '$lib/api/gpus';
	import { isAdmin } from '$lib/stores/auth';
	import Toggle from '$lib/components/notifications/Toggle.svelte';
	import ConfirmDialog from '$lib/components/ConfirmDialog.svelte';

	let gpus = $state<GpuView[]>([]);
	let loaded = $state(false);
	let error = $state<string | null>(null);
	let pending = $state<Set<string>>(new Set());
	let confirmTarget = $state<GpuView | null>(null);

	async function load() {
		try {
			gpus = await fetchGpus();
			error = null;
		} catch {
			error = 'Could not load the GPU inventory.';
		} finally {
			loaded = true;
		}
	}

	function dotStatus(g: GpuView): string {
		if (!g.enabled) return 'off';
		return g.status === 'available' ? 'ok' : 'warn';
	}

	function statusLabel(g: GpuView): string {
		if (!g.enabled) return 'disabled';
		return g.status === 'available' ? 'available' : 'busy';
	}

	async function toggle(g: GpuView, next: boolean) {
		pending = new Set(pending).add(g.id);
		try {
			const updated = await updateGpu(g.id, next);
			gpus = gpus.map((x) => (x.id === g.id ? updated : x));
			error = null;
		} catch {
			error = 'Saving the GPU switch failed.';
		} finally {
			const p = new Set(pending);
			p.delete(g.id);
			pending = p;
		}
	}

	async function removeConfirmed() {
		const g = confirmTarget;
		confirmTarget = null;
		if (!g) return;
		pending = new Set(pending).add(g.id);
		try {
			await deleteGpu(g.id);
			gpus = gpus.filter((x) => x.id !== g.id);
			error = null;
		} catch (e) {
			const msg = e instanceof Error ? e.message : '';
			error = msg.includes('409')
				? 'That GPU is in use by a running transcode. Disable it instead, or wait for the task to finish.'
				: 'Deleting the GPU failed.';
		} finally {
			const p = new Set(pending);
			p.delete(g.id);
			pending = p;
		}
	}

	onMount(load);
</script>

<section class="panel" data-testid="gpus-card">
	<h3 class="eyebrow">Transcode GPUs</h3>
	{#if error}
		<div class="alert alert-danger" role="alert">{error}</div>
	{/if}
	{#if !loaded}
		<p class="gpus-card-note">Loading GPU inventory...</p>
	{:else if gpus.length === 0}
		<p class="gpus-card-note" data-testid="gpus-empty">
			No GPUs configured. Transcodes run on CPU. The inventory seeds from the host probe (ARM_GPUS)
			when this list is empty and the backend restarts.
		</p>
	{:else}
		<div class="stack stack-sm">
			{#each gpus as g (g.id)}
				<div class="panel-section gpus-card-row" data-testid="gpu-row-{g.id}">
					<span class="status-dot" data-status={dotStatus(g)} aria-hidden="true"></span>
					<span class="badge gpus-card-vendor">{g.vendor.toUpperCase()}</span>
					<span class="gpus-card-device" title={g.device_path}>{g.device_path}</span>
					<span class="gpus-card-kinds">
						{#each g.encoder_kinds as kind (kind)}
							<span class="chip">{kind}</span>
						{/each}
					</span>
					<span class="gpus-card-status">{statusLabel(g)}</span>
					{#if $isAdmin}
						<Toggle
							checked={g.enabled}
							label="Enable {g.vendor} {g.device_path}"
							onchange={(next) => toggle(g, next)}
						/>
						<button
							type="button"
							class="btn btn-ghost btn-sm"
							disabled={pending.has(g.id)}
							aria-label="Delete {g.vendor} {g.device_path}"
							onclick={() => (confirmTarget = g)}
						>
							Delete
						</button>
					{/if}
				</div>
			{/each}
		</div>
		<p class="gpus-card-note">
			Seeded from the host probe on first boot. To re-probe, delete every row and restart the
			backend.
		</p>
	{/if}
</section>

{#if confirmTarget}
	<ConfirmDialog
		open={true}
		title="Delete GPU"
		message={`Remove ${confirmTarget.vendor.toUpperCase()} ${confirmTarget.device_path} from the inventory? The dispatcher will no longer use it. Deleting every row and restarting the backend re-seeds from the host probe.`}
		confirmLabel="Delete"
		onconfirm={removeConfirmed}
		oncancel={() => (confirmTarget = null)}
	/>
{/if}

<style>
	.gpus-card-row {
		display: flex;
		align-items: center;
		gap: 0.75rem;
	}
	.gpus-card-vendor {
		flex-shrink: 0;
	}
	.gpus-card-device {
		font-family: var(--font-mono);
		font-size: 0.8125rem;
		color: var(--color-text-muted);
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
		min-width: 0;
		flex: 1;
	}
	.gpus-card-kinds {
		display: flex;
		gap: 0.25rem;
		flex-shrink: 0;
	}
	.gpus-card-status {
		font-size: 0.8125rem;
		color: var(--color-text-muted);
		flex-shrink: 0;
		width: 4.5rem;
	}
	.gpus-card-note {
		font-size: 0.8125rem;
		color: var(--color-text-muted);
		margin-top: 0.75rem;
	}
</style>
