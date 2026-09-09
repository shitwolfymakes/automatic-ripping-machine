<script lang="ts">
	import Glyph from './Glyph.svelte';

	interface Props {
		dir: 'asc' | 'desc' | null;
		class?: string;
	}

	let { dir, class: className = '' }: Props = $props();
</script>

{#if dir === 'asc'}
	<Glyph name="chevron-up" class="table-sort-indicator {className}" />
{:else if dir === 'desc'}
	<Glyph name="chevron-down" class="table-sort-indicator {className}" />
{/if}

<style>
	/* :global: the class lands on the <svg> Glyph renders, a child component's markup, not an element in this template. */
	:global(.table-sort-indicator) {
		display: inline-block;
		width: 0.75rem;
		height: 0.75rem;
	}
</style>
