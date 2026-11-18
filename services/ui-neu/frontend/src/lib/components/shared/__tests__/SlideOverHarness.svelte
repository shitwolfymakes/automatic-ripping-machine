<script lang="ts">
	import SlideOver from '../SlideOver.svelte';

	interface Props {
		open?: boolean;
		onclose?: () => void;
		stacked?: boolean;
	}
	let { open = $bindable(true), onclose, stacked }: Props = $props();
</script>

<SlideOver bind:open title="Panel title" {onclose} {stacked}>
	<p data-testid="body">Body content</p>
</SlideOver>
