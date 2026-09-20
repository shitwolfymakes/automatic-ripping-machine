<script lang="ts">
	import SlideOver from '../SlideOver.svelte';

	interface Props { open?: boolean; onclose?: () => void; }
	let { open = $bindable(true), onclose }: Props = $props();
</script>

<SlideOver bind:open title="Panel title" {onclose}>
	<p data-testid="body">Body content</p>
</SlideOver>
