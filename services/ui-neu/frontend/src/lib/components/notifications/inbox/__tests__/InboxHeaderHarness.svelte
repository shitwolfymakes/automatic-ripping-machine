<script lang="ts">
	import InboxHeader from '../InboxHeader.svelte';

	// Holds the bound showCleared in real $state, as the notifications page
	// does, and shows it so a test can read back what the header wrote.
	let {
		unseenCount = 0,
		clearedCount = 0,
		purging = false,
		onpurge,
		ondismissall
	}: {
		unseenCount?: number;
		clearedCount?: number;
		purging?: boolean;
		onpurge: () => void;
		ondismissall: () => unknown;
	} = $props();

	let showCleared = $state(false);
</script>

<InboxHeader {unseenCount} {clearedCount} {purging} bind:showCleared {onpurge} {ondismissall} />
<output data-testid="show-cleared">{showCleared}</output>
