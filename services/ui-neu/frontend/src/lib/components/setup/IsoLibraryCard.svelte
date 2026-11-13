<script lang="ts">
	import { plural } from '$lib/utils/plural';
	import CopyBlock from '$lib/components/CopyBlock.svelte';
	import Glyph from '$lib/components/Glyph.svelte';
	import type { IsoStatus } from '$lib/utils/setup-drives';

	// Shows whether the ISO library is on, or how to turn it on.
	let { iso }: { iso: IsoStatus } = $props();
</script>

<section class="panel stack iso-library-card" data-testid="drives-iso">
	<div class="iso-library-card-head">
		<span class="iso-library-card-title"><Glyph name="disc-3" /> Rip from image files</span>
		<span class="chip chip-sm {iso.on ? 'chip-success' : ''}">
			<Glyph name={iso.on ? 'check-circle' : 'minus-circle'} class="h-3 w-3" />
			ISO library: {iso.on ? `on, ${iso.count} ${plural(iso.count, 'image')}` : 'off'}
		</span>
	</div>
	<p class="iso-library-card-help">ARM can rip ISO image files with no drive at all.</p>
	{#if iso.on && iso.path}
		<p class="iso-library-card-help">Images are read from <code class="mono">{iso.path}</code> on the server.</p>
	{/if}
	{#if !iso.on}
		<p class="iso-library-card-help">To turn it on, add this line to .env:</p>
		<CopyBlock text="ARM_HOST_ISO_LIBRARY_PATH=/path/to/your/isos" />
		<p class="iso-library-card-help">
			Then restart ARM; it mounts that folder read-only for you. <a href="/help">Read how</a>
		</p>
	{/if}
</section>

<style>
	.iso-library-card-head {
		display: flex;
		flex-wrap: wrap;
		align-items: center;
		justify-content: space-between;
		gap: 0.5rem;
	}
	.iso-library-card-title {
		display: inline-flex;
		align-items: center;
		gap: 0.5rem;
		font-weight: 600;
	}
	.iso-library-card-help {
		font-size: 0.875rem;
		color: var(--color-text-muted);
	}
</style>
