<script lang="ts">
	import SlideOver from '../SlideOver.svelte';

	let { onclosebase }: { onclosebase?: () => void } = $props();
</script>

<SlideOver open title="Base panel" onclose={onclosebase}>
	<p>Base body</p>
	{#snippet footer()}
		<p data-testid="footer">Footer</p>
	{/snippet}
</SlideOver>
<SlideOver open title="Top panel" stacked>
	<p>Top body</p>
</SlideOver>
