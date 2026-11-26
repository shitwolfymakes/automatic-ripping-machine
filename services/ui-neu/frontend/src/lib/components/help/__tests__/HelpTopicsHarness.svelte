<script lang="ts">
	import type { DocsNavSection } from '$lib/help/api';
	import HelpTopics from '../HelpTopics.svelte';

	// Holds the bound open in real $state, as the help page does, and shows it
	// so a test can read back what the topics list wrote.
	let { nav, activeId }: { nav: DocsNavSection[]; activeId: string } = $props();

	let open = $state(false);
</script>

<HelpTopics {nav} {activeId} bind:open />
<output data-testid="open">{open}</output>
