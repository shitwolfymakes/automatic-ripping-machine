<script lang="ts">
	import { onMount, onDestroy } from 'svelte';
	import type { ConfigView, DriveView, GpuView, SetupView } from '$lib/types/api.gen';
	import Glyph from '$lib/components/shared/Glyph.svelte';
	import FinishSummary from '../FinishSummary.svelte';
	import FirstDiscCard from '../FirstDiscCard.svelte';
	import { fetchDrives } from '$lib/api/drives';
	import { fetchConfigView } from '$lib/api/config';
	import { fetchGpus } from '$lib/api/gpus';
	import { fetchChannels } from '$lib/api/channels';
	import { createPollingStore } from '$lib/stores/polling';
	import { transcoderEnabled } from '$lib/stores/config';
	import { setupSummaries } from '$lib/settings/setup-summaries';
	import type { StepCommitResult } from '../../../setup/steps';

	// Step 9: the first disc, the summary, and the certificate (setup spec §5.10).
	let { view }: { view: SetupView; setBlocked?: (reason: string | null) => void } = $props();

	const drives = createPollingStore(fetchDrives, [] as DriveView[], 3000);
	const target = $derived(
		$drives.find((d) => d.lifecycle === 'enrolled' && d.kind !== 'virtual' && d.status !== 'offline') ?? null
	);
	let config = $state<ConfigView | null>(null);
	let gpus = $state<GpuView[]>([]);
	let channelCount = $state(0);

	/**
	 * Loads what the summary lines need besides the drives. A load that
	 * fails leaves its value at the default.
	 */
	async function loadSummaryData(): Promise<void> {
		const [c, g, ch] = await Promise.allSettled([fetchConfigView(), fetchGpus(), fetchChannels()]);
		if (c.status === 'fulfilled') config = c.value;
		if (g.status === 'fulfilled') gpus = g.value;
		if (ch.status === 'fulfilled') channelCount = ch.value.filter((x) => (x.type as string) !== 'inapp').length;
	}

	onMount(() => {
		drives.start();
		void loadSummaryData();
	});
	onDestroy(() => drives.stop());

	const summaries = $derived(
		setupSummaries({ view, drives: $drives, config, gpus, channelCount, transcoderEnabled: $transcoderEnabled })
	);

	export async function commit(): Promise<StepCommitResult> {
		return 'done';
	}
</script>

<div class="stack stack-lg">
	<FirstDiscCard {target} />

	<section class="panel stack">
		<h2 class="finish-step-title">Your setup</h2>
		<FinishSummary {view} {summaries} />
	</section>

	<section class="panel stack" data-testid="finish-cert">
		<div class="finish-step-cert-head">
			<div>
				<h2 class="finish-step-title">
					<Glyph name="shield-check" class="inline h-5 w-5" /> Did your browser warn about the certificate?
				</h2>
				<p class="finish-step-help">ARM made its own certificate. Trust it on this device to remove the warning.</p>
			</div>
			<a class="btn btn-sm" href="/arm-ca.crt" download="arm-ca.crt"><Glyph name="download" /> Download certificate</a>
		</div>
		<details class="finish-step-howto">
			<summary>How to trust it</summary>
			<ul>
				<li>
					<strong>Windows:</strong> open the file, choose Install Certificate, then put it in Trusted Root Certification Authorities.
				</li>
				<li><strong>macOS:</strong> open the file in Keychain Access, then set it to Always Trust.</li>
				<li><strong>Linux and Firefox:</strong> import it under Settings, Certificates, Authorities.</li>
			</ul>
		</details>
	</section>
</div>

<style>
	.finish-step-title {
		font-size: 1.0625rem;
		font-weight: 600;
	}
	.finish-step-help {
		font-size: 0.875rem;
		color: var(--color-text-muted);
	}
	.finish-step-cert-head {
		display: flex;
		flex-wrap: wrap;
		align-items: flex-start;
		justify-content: space-between;
		gap: 0.75rem;
	}
	.finish-step-howto summary {
		cursor: pointer;
		color: var(--color-primary-text);
		font-weight: 600;
	}
	.finish-step-howto ul {
		display: grid;
		gap: 0.375rem;
		margin-top: 0.5rem;
		padding-left: 1.25rem;
		font-size: 0.875rem;
		color: var(--color-text-muted);
	}
</style>
