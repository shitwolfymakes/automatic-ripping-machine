<script lang="ts">
	import Glyph from './Glyph.svelte';

	interface Props {
		dir: 'asc' | 'desc' | null;
		class?: string;
	}

	let { dir, class: className = '' }: Props = $props();
</script>

{#if dir === 'asc'}
	<Glyph name="chevron-up" class="h-3 w-3 inline-block {className}" />
{:else if dir === 'desc'}
	<Glyph name="chevron-down" class="h-3 w-3 inline-block {className}" />
{/if}
