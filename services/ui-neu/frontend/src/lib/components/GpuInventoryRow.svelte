<script lang="ts">
	import type { Snippet } from 'svelte';
	import type { GpuView } from '$lib/types/api.gen';

	// One GPU in the inventory: status dot, vendor badge, device path and a
	// state word. Shared by Settings > GPUs (which adds the encoder chips and
	// the row controls through the snippets) and the Transcoder page's
	// read-only list, so the two never drift apart.
	let { gpu, kinds, controls }: { gpu: GpuView; kinds?: Snippet; controls?: Snippet } = $props();

	const VENDOR_LABEL: Record<string, string> = { nvenc: 'NVENC', qsv: 'Quick Sync', vaapi: 'VAAPI' };

	const dot = $derived(!gpu.enabled ? 'off' : gpu.status === 'available' ? 'ok' : 'warn');
	const state = $derived(!gpu.enabled ? 'disabled' : gpu.status === 'available' ? 'available' : 'busy');
</script>

<div class="gpu-inventory-row">
	<span class="status-dot" data-status={dot} aria-hidden="true"></span>
	<span class="badge gpu-inventory-row-vendor">{VENDOR_LABEL[gpu.vendor] ?? gpu.vendor.toUpperCase()}</span>
	<span class="gpu-inventory-row-device" title={gpu.device_path}>{gpu.device_path}</span>
	{@render kinds?.()}
	<span class="gpu-inventory-row-state">{state}</span>
	{@render controls?.()}
</div>

<style>
	.gpu-inventory-row {
		display: flex;
		align-items: center;
		gap: 0.75rem;
		font-size: 0.8125rem;
	}
	.gpu-inventory-row-vendor {
		flex-shrink: 0;
	}
	.gpu-inventory-row-device {
		font-family: var(--font-mono);
		color: var(--color-text-muted);
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
		min-width: 0;
		flex: 1;
	}
	.gpu-inventory-row-state {
		color: var(--color-text-muted);
		flex-shrink: 0;
		width: 4.5rem;
	}
</style>
