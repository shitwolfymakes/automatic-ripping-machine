<script lang="ts">
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
		<svg class="h-4 w-4 chevron" fill="none" stroke="currentColor" viewBox="0 0 24 24">
			<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 5l7 7-7 7" />
		</svg>
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
	.job-detail-section-title .chevron {
		transition: transform var(--motion-fast) var(--ease);
	}
	.job-detail-section-title[aria-expanded='true'] .chevron {
		transform: rotate(90deg);
	}
	.job-detail-raw-metadata {
		border: 1px solid var(--color-border);
		border-radius: var(--radius-lg);
		padding: 0.75rem;
	}
</style>
