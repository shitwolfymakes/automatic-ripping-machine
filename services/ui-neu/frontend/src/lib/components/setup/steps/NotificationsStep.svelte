<script lang="ts">
	import type { SetupView } from '$lib/types/api.gen';
	import ChannelQuickAdd from '$lib/components/notifications/ChannelQuickAdd.svelte';
	import type { StepCommitResult } from '../steps';

	// Step 8 (optional): one phone or chat channel (setup spec §5.9). Continue
	// with nothing picked is the same as Skip.
	let { view }: { view: SetupView; setBlocked?: (reason: string | null) => void } = $props();
	void view;
	let quick: ChannelQuickAdd | undefined = $state();
	let error = $state<string | null>(null);

	export async function commit(): Promise<StepCommitResult> {
		if (!quick) return 'skip';
		error = null;
		try {
			return (await quick.save()) === 'created' ? 'done' : 'skip';
		} catch (e) {
			error = e instanceof Error ? e.message : 'Adding the channel failed';
			return false;
		}
	}
</script>

<section class="panel">
	<ChannelQuickAdd bind:this={quick} />
	{#if error}<p class="alert alert-danger mt-3" role="alert">{error}</p>{/if}
</section>
