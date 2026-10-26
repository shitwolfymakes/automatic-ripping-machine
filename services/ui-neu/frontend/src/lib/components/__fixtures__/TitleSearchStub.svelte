<script lang="ts">
	// Stands in for TitleSearch where a test only needs its callbacks.
	let { onseries, initialType }: { onseries?: () => void; initialType?: 'movie' | 'tv' } = $props();
</script>

<button type="button" onclick={() => onseries?.()}>Pick a series</button>
<span data-testid="title-initial-type">{initialType ?? 'none'}</span>
