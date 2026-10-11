<script lang="ts">
	import { onMount } from 'svelte';
	import type { SetupView } from '$lib/types/api.gen';
	import GpusCard from '$lib/components/settings/GpusCard.svelte';
	import { fetchSystemDiagnostics } from '$lib/api/system';
	import { transcoderEnabled } from '$lib/stores/config';
	import SetupConfigFields from '../SetupConfigFields.svelte';
	import type { StepCommitResult } from '../steps';

	// Step 7 (optional): graphics devices with a live encoder test, and the
	// encode switches (setup spec §5.8). A ripper-only install has nothing to set.
	let { view }: { view: SetupView; setBlocked?: (reason: string | null) => void } = $props();
	void view;
	let fields: SetupConfigFields | undefined = $state();
	let location = $state<{ label: string } | null>(null);

	onMount(async () => {
		if (!$transcoderEnabled) return;
		try {
			const tc = (await fetchSystemDiagnostics()).checks.find((c) => c.name === 'transcoder');
			if (tc?.location === 'remote') location = { label: `Remote host ${tc.remote_host ?? ''}`.trim() };
			else if (tc?.location === 'local') location = { label: 'This server' };
		} catch {
			location = null;
		}
	});

	export async function commit(): Promise<StepCommitResult> {
		if (!$transcoderEnabled) return 'done';
		if (!fields || !(await fields.save())) return false;
		return 'done';
	}
</script>

{#if !$transcoderEnabled}
	<section class="panel" data-testid="transcoding-ripper-only">
		<p>This install only rips; encoding happens elsewhere or not at all.</p>
	</section>
{:else}
	<div class="stack stack-lg">
		<GpusCard {location} />
		<SetupConfigFields bind:this={fields} step="transcoding" />
	</div>
{/if}
