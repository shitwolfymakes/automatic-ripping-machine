<script lang="ts">
	import EditorSidebar from '../EditorSidebar.svelte';

	interface Props {
		onclose?: () => void;
		stacked?: boolean;
		width?: 'form' | 'wide';
		withActions?: boolean;
		withFooter?: boolean;
	}
	let { onclose = () => {}, stacked, width = 'form', withActions = true, withFooter = true }: Props = $props();
</script>

{#snippet footer()}
	<span>Footer content</span>
{/snippet}

<EditorSidebar title="Editor title" {width} {stacked} footer={withFooter ? footer : undefined} {onclose}>
	{#snippet headerActions()}
		{#if withActions}<button type="button">Header action</button>{/if}
	{/snippet}
	<p data-testid="body">Body content</p>
</EditorSidebar>
