<script lang="ts">
	import type { SetupStatus } from '$lib/api/setup';
	import { onMount } from 'svelte';
	import InfoCard from './InfoCard.svelte';
	import StatusIcon from './StatusIcon.svelte';
	import { transcoderEnabled } from '$lib/stores/config';

	interface Props {
		status: SetupStatus;
	}

	let { status }: Props = $props();

	let systemInfo = $state<{ cpu: string; memory_total_gb: number } | null>(null);
	let transcoderOnline = $state<boolean | null>(null);
	let transcoderStats = $state<{ pending: number; completed: number; worker_running: boolean } | null>(null);

	onMount(async () => {
		try {
			const resp = await fetch('/api/system-info');
			if (resp.ok) systemInfo = await resp.json();
		} catch { /* non-critical */ }

		if (!$transcoderEnabled) return;
		try {
			const resp = await fetch('/api/dashboard');
			if (resp.ok) {
				const data = await resp.json();
				transcoderOnline = data.transcoder_online ?? false;
				transcoderStats = data.transcoder_stats ?? null;
			}
		} catch { /* non-critical */ }
	});
</script>

<div class="stack stack-lg">
	<div class="welcome-step-header">
		<h2 class="welcome-step-title">Welcome to ARM</h2>
		<p class="welcome-step-subtitle">
			Let's make sure your system is configured correctly.
		</p>
	</div>

	<div class="grid-2">
		<InfoCard label="ARM Version">
			<span class="welcome-step-value">{status.arm_version}</span>
		</InfoCard>

		<InfoCard label="Database">
			<span class="cluster">
				<StatusIcon ok={!!status.db_initialized} />
				<span class="welcome-step-value" data-tone={status.db_initialized ? 'ok' : 'warn'}>
					{status.db_initialized ? 'Initialized' : 'Not initialized'}
				</span>
			</span>
		</InfoCard>

		{#if systemInfo}
			<InfoCard label="CPU">
				<span class="truncate welcome-step-value-sm" title={systemInfo.cpu}>
					{systemInfo.cpu}
				</span>
			</InfoCard>

			<InfoCard label="Memory">
				<span class="welcome-step-value">
					{systemInfo.memory_total_gb.toFixed(1)} GB
				</span>
			</InfoCard>
		{/if}
	</div>

	<div class="grid-2 welcome-step-status-row {$transcoderEnabled ? '' : 'welcome-step-status-row-single'}">
		<InfoCard label="Drives">
			<span class="welcome-step-value-sm">{status.setup_steps?.drives ?? '?'}</span>
		</InfoCard>

		{#if $transcoderEnabled}
			<InfoCard label="Transcoder">
				{#if transcoderOnline === null}
					<span class="welcome-step-value-sm" data-tone="wait">Checking...</span>
				{:else}
					<span class="cluster">
						<StatusIcon ok={transcoderOnline} />
						<span class="welcome-step-value-sm" data-tone={transcoderOnline ? 'ok' : 'off'}>
							{transcoderOnline ? 'Online' : 'Offline'}
						</span>
					</span>
				{/if}
			</InfoCard>

			<InfoCard label="Transcoder DB">
				{#if transcoderOnline === null}
					<span class="welcome-step-value-sm" data-tone="wait">Checking...</span>
				{:else}
					<span class="cluster">
						<StatusIcon ok={!!(transcoderOnline && transcoderStats)} />
						<span class="welcome-step-value-sm" data-tone={transcoderOnline && transcoderStats ? 'ok' : 'off'}>
							{transcoderOnline && transcoderStats ? 'Ready' : 'Unavailable'}
						</span>
					</span>
				{/if}
			</InfoCard>
		{/if}
	</div>
</div>

<style>
	.welcome-step-header { text-align: center; }
	.welcome-step-title { font-size: 1.5rem; line-height: 2rem; font-weight: 700; color: var(--color-text); }
	.welcome-step-subtitle { margin-top: 0.5rem; color: var(--color-text-muted); }
	.welcome-step-value { font-size: 1.125rem; line-height: 1.75rem; font-weight: 500; color: var(--color-text); }
	.welcome-step-value-sm { font-size: 0.875rem; line-height: 1.25rem; font-weight: 500; color: var(--color-text); }
	/* status tones dissolved from legacy.css's .setup-status-* rules
	   (Task 11): ok/warn use the same green/red pairing the legacy rules
	   did, off/wait are muted text (off had no dark: variant in the
	   original, so it stays --color-text-faint in both modes) */
	.welcome-step-value[data-tone="ok"], .welcome-step-value-sm[data-tone="ok"] { color: var(--color-success); }
	.welcome-step-value[data-tone="warn"] { color: var(--color-danger); }
	.welcome-step-value-sm[data-tone="off"] { color: var(--color-text-muted); }
	/* original .setup-status-wait was text-gray-400 with NO dark: variant,
	   so it stayed gray-400 in both modes; --color-text-faint is gray-400 in
	   light but gray-500 in dark, so dark mode needs --color-text-muted
	   (gray-400 there) instead to keep the same rendered shade */
	.welcome-step-value-sm[data-tone="wait"] { color: var(--color-text-faint); }
	/* :global: dark-mode override, see the comment above */
	:global(.dark) .welcome-step-value-sm[data-tone="wait"] { color: var(--color-text-muted); }
	@media (min-width: 640px) {
		.welcome-step-status-row { grid-template-columns: repeat(3, minmax(0, 1fr)); }
		.welcome-step-status-row-single { grid-template-columns: 1fr; }
	}
</style>
