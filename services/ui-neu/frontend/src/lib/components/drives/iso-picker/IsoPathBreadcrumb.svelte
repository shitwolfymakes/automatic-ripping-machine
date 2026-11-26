<script lang="ts">
	// The ISO picker's library breadcrumb: a link for every folder above the
	// one being shown, then the current folder as plain text.
	import Glyph from '../../shared/Glyph.svelte';

	interface Props {
		/** The trail, from the library root to the folder being shown. */
		items: { label: string; path: string }[];
		/** Called with a folder's path when its link is clicked. */
		onnavigate: (path: string) => void;
	}

	let { items, onnavigate }: Props = $props();
</script>

<nav class="iso-picker-breadcrumb" aria-label="Library">
	{#each items as item, i (item.path)}
		{#if i > 0}
			<Glyph name="chevron-right" class="h-3 w-3 iso-picker-breadcrumb-sep" />
		{/if}
		{#if i === items.length - 1}
			<span class="iso-picker-breadcrumb-current" aria-current="page">{item.label}</span>
		{:else}
			<button type="button" class="iso-picker-breadcrumb-link" onclick={() => onnavigate(item.path)}>
				{item.label}
			</button>
		{/if}
	{/each}
</nav>

<style>
	.iso-picker-breadcrumb {
		display: flex;
		align-items: center;
		gap: 0.25rem;
		font-size: 0.875rem;
		line-height: calc(1.25 / 0.875);
	}
	.iso-picker-breadcrumb-link {
		border: 0;
		background: none;
		padding: 0;
		cursor: pointer;
		color: var(--color-primary-text);
		text-decoration: underline;
	}
	.iso-picker-breadcrumb-current {
		font-weight: 600;
		color: var(--color-text);
	}
	/* :global: forwarded through Glyph's class prop */
	:global(.iso-picker-breadcrumb-sep) {
		color: var(--color-text-faint);
	}
</style>
