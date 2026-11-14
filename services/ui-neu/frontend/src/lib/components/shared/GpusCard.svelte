<!-- Settings > GPUs: the DB-authoritative transcode GPU inventory (G-30).
     Rows are seeded from the host probe (ARM_GPUS) only while the table is
     empty; after that this card is how operators manage devices. Disable
     keeps a device listed but the dispatcher never claims it; delete needs
     confirmation and is refused by the server (409) while a running
     transcode holds the claim. -->
<script lang="ts">
	import { errorMessage } from '$lib/utils/errors';
	import { onMount } from 'svelte';
	import type { GpuView } from '$lib/types/api.gen';
	import { fetchGpus, updateGpu, deleteGpu, probeGpu, probeAllGpus } from '$lib/api/gpus';
	import { ApiError } from '$lib/api/client';
	import { wsClient, type WSEnvelope } from '$lib/api/ws';
	import { isAdmin } from '$lib/stores/auth';
	import { encodersStore } from '$lib/stores/encoders.svelte';
	import Toggle from '$lib/components/shared/Toggle.svelte';
	import ConfirmDialog from '$lib/components/shared/ConfirmDialog.svelte';
	import Glyph from '$lib/components/shared/Glyph.svelte';
	import GpuEncoderChips from './GpuEncoderChips.svelte';
	import GpuInventoryRow from '$lib/components/shared/GpuInventoryRow.svelte';
	import StatusStrip from '$lib/components/shared/StatusStrip.svelte';
	import { PendingKeys } from '../../stores/pending-keys.svelte';
	import { ProbeTimers } from '../../stores/settings-probe-timers.svelte';

	// Shared by Settings > Transcoding and the setup walkthrough's Transcoding
	// step. A probe is a real test encode run in a container (10-60 s); its
	// result arrives as a `gpu.probed` event, so each device shows its own
	// in-progress state until that event (or a 2-minute timeout).
	let { location = null }: { location?: { label: string } | null } = $props();

	let gpus = $state<GpuView[]>([]);
	let loaded = $state(false);
	let error = $state<string | null>(null);
	const pending = new PendingKeys();
	let probingAll = $state(false);
	let confirmTarget = $state<GpuView | null>(null);
	const probes = new ProbeTimers();

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

	async function reprobe(g: GpuView) {
		await pending.run(g.id, async () => {
			try {
				await probeGpu(g.id);
				probes.start([g.id]);
				error = null;
			} catch (e) {
				error = errorMessage(e, 'Re-probe failed.');
			}
		});
	}

	async function reprobeAll() {
		probingAll = true;
		try {
			await probeAllGpus();
			probes.start(gpus.filter((g) => g.enabled).map((g) => g.id));
			error = null;
		} catch (e) {
			error = errorMessage(e, 'Re-probe failed.');
		} finally {
			probingAll = false;
		}
	}

	async function toggle(g: GpuView, next: boolean) {
		await pending.run(g.id, async () => {
			try {
				const updated = await updateGpu(g.id, next);
				gpus = gpus.map((x) => (x.id === g.id ? updated : x));
				error = null;
				encodersStore.refresh();
			} catch {
				error = 'Saving the GPU switch failed.';
			}
		});
	}

	async function removeConfirmed() {
		const g = confirmTarget;
		confirmTarget = null;
		if (!g) return;
		await pending.run(g.id, async () => {
			try {
				await deleteGpu(g.id);
				gpus = gpus.filter((x) => x.id !== g.id);
				error = null;
				encodersStore.refresh();
			} catch (e) {
				// The client puts the server's detail in the message; the status is the signal.
				error =
					e instanceof ApiError && e.status === 409
						? 'That GPU is in use by a running transcode. Disable it instead, or wait for the task to finish.'
						: 'Deleting the GPU failed.';
			}
		});
	}

	onMount(() => {
		load();
		// Start the socket ourselves: on the setup walkthrough no other store has.
		wsClient.start();
		const unsubscribe = wsClient.subscribe('transcode.events', (env: WSEnvelope) => {
			// The encoders store follows gpu.probed itself.
			if (env.event_type !== 'gpu.probed') return;
			const id = (env.payload as { gpu_id?: string }).gpu_id;
			if (id) probes.stop(id);
			load();
		});
		return () => {
			unsubscribe?.();
			probes.dispose();
		};
	});
</script>

<section class="panel gpus-card" data-testid="gpus-card">
	<div class="gpus-card-head">
		<h3 class="eyebrow">Transcode GPUs</h3>
		{#if $isAdmin && gpus.length > 0}
			<button type="button" class="btn btn-sm" disabled={probingAll} onclick={reprobeAll}>
				<Glyph name="refresh" class="h-3.5 w-3.5" /> Test encoders
			</button>
		{/if}
	</div>
	{#if location}
		<p class="gpus-card-location">
			<Glyph name="cpu" /> Encoding runs on <span class="chip chip-sm chip-info">{location.label}</span>
		</p>
	{/if}
	{#if error}
		<div class="alert alert-danger" role="alert">{error}</div>
	{/if}
	{#if !loaded}
		<p class="gpus-card-note">Loading GPU inventory...</p>
	{:else if gpus.length === 0}
		<p class="gpus-card-note" data-testid="gpus-empty">
			ARM will encode on the CPU. It works, just slower. The inventory seeds from the host probe (ARM_GPUS) when this
			list is empty and the backend restarts.
		</p>
	{:else}
		<div class="stack stack-sm gpus-card-list">
			{#each gpus as g (g.id)}
				<div class="panel-section gpus-card-row-wrap" data-testid="gpu-row-{g.id}">
					<GpuInventoryRow gpu={g}>
						{#snippet kinds()}
							<GpuEncoderChips gpu={g} />
						{/snippet}
						{#snippet controls()}
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
									aria-label="Re-probe {g.vendor} {g.device_path}"
									onclick={() => reprobe(g)}
								>
									Re-probe
								</button>
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
						{/snippet}
					</GpuInventoryRow>
					{#if probes.isProbing(g.id)}
						<StatusStrip tone="busy" title="Testing encoders..." detail="Takes 10 to 60 seconds" progress />
					{:else if probes.timedOut(g.id)}
						<StatusStrip tone="danger" title="Couldn't test" detail="No result after 2 minutes. Try Re-probe." />
					{/if}
					{#if g.probe_error}
						<p class="mono field-error" data-testid="gpu-probe-error-{g.id}">{g.probe_error}</p>
					{/if}
				</div>
			{/each}
		</div>
		<p class="gpus-card-note">
			Rows come from device discovery; each device's encoders are verified by a per-device probe. Use Re-probe to
			re-verify a device without restarting the backend.
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
	/* same padding as the Settings section cards it sits beside */
	.gpus-card {
		padding: 1.5rem;
	}
	.gpus-card-head {
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: 0.75rem;
	}
	.gpus-card-row-wrap {
		display: flex;
		flex-direction: column;
		gap: 0.375rem;
	}
	.gpus-card-location {
		display: flex;
		align-items: center;
		gap: 0.5rem;
		margin-top: 0.5rem;
		font-size: 0.875rem;
		color: var(--color-text);
	}
	/* keeps the first GPU row clear of the header row and its Test encoders button */
	.gpus-card-list {
		margin-top: 0.75rem;
	}
	.gpus-card-note {
		font-size: 0.8125rem;
		color: var(--color-text-muted);
		margin-top: 0.75rem;
	}
</style>
