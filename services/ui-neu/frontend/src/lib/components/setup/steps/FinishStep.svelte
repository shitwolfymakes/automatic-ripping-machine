<script lang="ts">
	import { onMount, onDestroy } from 'svelte';
	import type { ConfigView, DriveView, GpuView, SetupView } from '$lib/types/api.gen';
	import Glyph from '$lib/components/Glyph.svelte';
	import FinishSummary from '../FinishSummary.svelte';
	import { fetchDrives } from '$lib/api/drives';
	import { fetchConfigView } from '$lib/api/config';
	import { fetchGpus } from '$lib/api/gpus';
	import { fetchChannels } from '$lib/api/channels';
	import { fetchUsers } from '$lib/api/users';
	import { wsClient, type WSEnvelope } from '$lib/api/ws';
	import { createPollingStore } from '$lib/stores/polling';
	import { transcoderEnabled } from '$lib/stores/config';
	import { driveTitle } from '$lib/utils/drives';
	import type { StepCommitResult } from '../steps';

	// Step 9: the first disc, the summary, and the certificate (setup spec §5.10).
	let { view }: { view: SetupView; setBlocked?: (reason: string | null) => void } = $props();

	const drives = createPollingStore(fetchDrives, [] as DriveView[], 3000);
	const target = $derived(
		$drives.find((d) => d.lifecycle === 'enrolled' && d.kind !== 'virtual' && d.status !== 'offline') ?? null
	);
	let ripStarted = $state(false);
	let config = $state<ConfigView | null>(null);
	let gpus = $state<GpuView[]>([]);
	let channelCount = $state(0);
	let guestOn = $state<boolean | null>(null);

	onMount(() => {
		drives.start();
		void (async () => {
			const [c, g, ch, u] = await Promise.allSettled([fetchConfigView(), fetchGpus(), fetchChannels(), fetchUsers()]);
			if (c.status === 'fulfilled') config = c.value;
			if (g.status === 'fulfilled') gpus = g.value;
			if (ch.status === 'fulfilled') channelCount = ch.value.filter((x) => (x.type as string) !== 'inapp').length;
			if (u.status === 'fulfilled') guestOn = u.value.some((x) => x.role === 'guest' && !x.disabled);
		})();
		wsClient.start();
		const unsubscribe = wsClient.subscribe('ripper.events', (env: WSEnvelope) => {
			if (env.event_type === 'rip.started' && target && env.payload.drive_id === target.id) ripStarted = true;
		});
		return () => unsubscribe?.();
	});
	onDestroy(() => drives.stop());

	const summaries = $derived.by(() => {
		const enrolled = $drives.filter((d) => d.lifecycle === 'enrolled' && d.kind !== 'virtual').length;
		const ignored = $drives.filter((d) => d.lifecycle === 'ignored').length;
		const keys = config
			? ['tmdb_api_key', 'omdb_api_key', 'tvdb_api_key'].filter((k) => !!config?.[k as keyof ConfigView]).length
			: 0;
		const out: Record<string, string> = {
			account: `Password changed.${guestOn === null ? '' : ` Guest access ${guestOn ? 'on' : 'off'}.`}`,
			system:
				view.progress.system?.state === 'attention'
					? 'Needs a fix on the server, see System check.'
					: 'All checks pass.',
			drives: `${enrolled} enrolled, ${ignored} ignored`,
			notifications: channelCount ? `${channelCount} channel${channelCount === 1 ? '' : 's'}` : 'Inbox only'
		};
		if (config) {
			out.makemkv = `${config.makemkv_key ? 'Purchased key' : 'Free beta key'}${config.makemkv_key_valid ? ', valid' : ''}`;
			out.metadata = keys
				? `${keys} key${keys === 1 ? '' : 's'} saved. Titles looked up with ${config.metadata_provider === 'omdb' ? 'OMDb' : 'TMDb'}.`
				: 'No lookup key yet';
			out.discs = !config.auto_rip_on_insert ? 'Manual' : config.hold_for_review ? 'Review first' : 'Fully automatic';
		}
		out.transcoding = !$transcoderEnabled
			? 'Ripper only'
			: gpus.some((g) => g.enabled)
				? `${gpus.filter((g) => g.enabled).length} graphics device${gpus.filter((g) => g.enabled).length === 1 ? '' : 's'} enabled`
				: 'CPU encoding';
		return out;
	});

	export async function commit(): Promise<StepCommitResult> {
		return 'done';
	}
</script>

<div class="stack stack-lg">
	<section class="panel finish-step-disc" data-testid="finish-disc">
		<span class="finish-step-disc-icon" aria-hidden="true"><Glyph name="disc-3" class="h-7 w-7" /></span>
		<div class="stack stack-sm">
			<h2 class="finish-step-title">Insert a disc to try it</h2>
			<p class="finish-step-status" role="status" aria-live="polite">
				{#if !target}
					<a href="/setup/drives">Enroll a drive to try it.</a>
				{:else if ripStarted}
					<Glyph name="check-circle" /> Ripping started in {driveTitle(target)}
				{:else if target.media_status === 'loaded'}
					<Glyph name="check-circle" /> Disc detected in {driveTitle(target)}
				{:else}
					<span class="finish-step-dot" aria-hidden="true"></span> Waiting for a disc in {driveTitle(target)}...
				{/if}
			</p>
			<p class="finish-step-help">
				Put any DVD, Blu-ray or CD in the drive. You can leave this page; the rip carries on.
			</p>
		</div>
	</section>

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
	.finish-step-disc {
		display: flex;
		align-items: flex-start;
		gap: 1rem;
		border: 1px solid var(--color-primary);
		padding: 1.25rem;
	}
	.finish-step-disc-icon {
		flex: none;
		display: grid;
		place-items: center;
		width: 3.25rem;
		height: 3.25rem;
		border-radius: var(--radius-lg);
		background: var(--color-primary-tint-2);
		color: var(--color-primary-text);
	}
	.finish-step-title {
		font-size: 1.0625rem;
		font-weight: 600;
	}
	.finish-step-status {
		display: flex;
		align-items: center;
		gap: 0.5rem;
		font-weight: 600;
	}
	.finish-step-dot {
		width: 0.5rem;
		height: 0.5rem;
		border-radius: 999px;
		background: var(--color-primary);
		animation: finish-step-pulse 1.6s ease-in-out infinite;
	}
	@keyframes finish-step-pulse {
		50% {
			opacity: 0.35;
		}
	}
	@media (prefers-reduced-motion: reduce) {
		.finish-step-dot {
			animation: none;
		}
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
