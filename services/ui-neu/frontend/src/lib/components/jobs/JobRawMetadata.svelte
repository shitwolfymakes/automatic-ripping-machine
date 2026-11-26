<script lang="ts">
	import Glyph from '$lib/components/shared/Glyph.svelte';
	import JsonTree from '$lib/components/shared/JsonTree.svelte';

	interface Props {
		pairs: [string, unknown][];
	}

	let { pairs }: Props = $props();

	let showRawMetadata = $state(false);
</script>

<section>
	<button
		type="button"
		onclick={() => {
			showRawMetadata = !showRawMetadata;
		}}
		class="flex w-full items-center gap-2 job-detail-section-title"
		aria-expanded={showRawMetadata}
	>
		<Glyph name="chevron-right" class="h-4 w-4 chevron" />
		Raw metadata
	</button>
	{#if showRawMetadata}
		<div class="mt-3 overflow-x-auto job-detail-raw-metadata">
			{#each pairs as [key, value] (key)}
				<JsonTree {value} name={key} depth={0} />
			{/each}
		</div>
	{/if}
</section>

<style>
	.job-detail-section-title {
		font-size: 1.125rem;
		line-height: 1.75rem;
		font-weight: 600;
		color: var(--color-text);
	}
	/* :global: set on Glyph through its class prop */
	.job-detail-section-title :global(.chevron) {
		transition: transform var(--motion-fast) var(--ease);
	}
	/* :global: set on Glyph through its class prop */
	.job-detail-section-title[aria-expanded='true'] :global(.chevron) {
		transform: rotate(90deg);
	}
	.job-detail-raw-metadata {
		border: 1px solid var(--color-border);
		border-radius: var(--radius-lg);
		padding: 0.75rem;
	}
</style>
