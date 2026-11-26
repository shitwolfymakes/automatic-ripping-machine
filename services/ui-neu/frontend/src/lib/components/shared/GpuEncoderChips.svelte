<script lang="ts">
	// A GPU's encoder chips in Settings > GPUs, saying whether it was tested and
	// which encoders its probe verified.
	import type { GpuView } from '$lib/types/api.gen';
	import Glyph from '$lib/components/shared/Glyph.svelte';

	let { gpu }: { gpu: GpuView } = $props();
</script>

<span class="gpu-encoder-chips">
	{#if !gpu.probed_at}
		<span class="chip chip-sm"><Glyph name="clock" class="h-3 w-3" />Not tested</span>
	{:else if gpu.encoder_kinds.length === 0}
		<span class="chip chip-sm chip-danger"><Glyph name="x" class="h-3 w-3" />Nothing verified</span>
	{:else}
		{#each gpu.encoder_kinds as kind (kind)}
			<span class="chip chip-sm chip-success"><Glyph name="check" class="h-3 w-3" />{kind.toUpperCase()} available</span
			>
		{/each}
	{/if}
</span>

<style>
	.gpu-encoder-chips {
		display: flex;
		flex-wrap: wrap;
		gap: 0.25rem;
		flex-shrink: 0;
	}
</style>
