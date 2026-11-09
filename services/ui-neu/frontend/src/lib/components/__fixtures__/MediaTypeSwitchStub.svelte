<script lang="ts">
	// Stands in for MediaTypeSwitch: shows the hand-set count the card passes
	// and reports a type change without calling the API.
	let { handSetCount, onchanged }: { handSetCount: number; onchanged: (type: 'movie' | 'tv') => void } = $props();
</script>

<span data-testid="hand-set-count">{handSetCount}</span>
<button type="button" onclick={() => onchanged('movie')}>Switch to Movie</button>
<button type="button" onclick={() => onchanged('tv')}>Switch to TV</button>
