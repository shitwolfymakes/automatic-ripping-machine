<script lang="ts">
	import Flyout from '../Flyout.svelte';
	import FlyoutItem from '../FlyoutItem.svelte';

	interface Props {
		onaction?: () => void;
		align?: 'left' | 'right';
	}
	let { onaction = () => {}, align = 'right' }: Props = $props();
</script>

<!-- An "outside" target to test click-away dismissal -->
<button type="button" data-testid="outside">outside</button>

<Flyout {align} width="w-52" label="Test menu">
	{#snippet trigger({ toggle, open })}
		<button type="button" data-testid="trigger" aria-expanded={open} onclick={toggle}>Open</button>
	{/snippet}
	{#snippet children({ close })}
		<FlyoutItem
			onclick={() => {
				onaction();
				close();
			}}>Do thing</FlyoutItem
		>
	{/snippet}
</Flyout>
