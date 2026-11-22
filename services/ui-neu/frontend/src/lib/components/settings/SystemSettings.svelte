<script lang="ts">
	import { onMount } from 'svelte';
	import type { SetupRestart } from '$lib/stores/setupRestart.svelte';
	import SystemHealth from '$lib/components/settings/SystemHealth.svelte';
	import EnvironmentSection from '$lib/components/settings/EnvironmentSection.svelte';
	import ContainersSection from '$lib/components/settings/ContainersSection.svelte';
	import CopyReportButton from '$lib/components/settings/CopyReportButton.svelte';
	import { fetchSystemDiagnostics, fetchSystemEnvironment } from '$lib/api/system';
	import { fetchDiagnostics } from '$lib/api/diagnostics';
	import { buildDeploymentReport } from '$lib/utils/deployment-report';
	import type {
		DiagnosticsServiceView,
		SystemDiagnosticsResponse,
		SystemEnvironmentResponse
	} from '$lib/types/api.gen';

	interface Props {
		setup: SetupRestart;
	}

	let { setup }: Props = $props();

	let env = $state<SystemEnvironmentResponse | null>(null);
	let envError = $state<string | null>(null);
	let logLevels = $state<DiagnosticsServiceView[]>([]);
	let logError = $state<string | null>(null);
	let health: SystemDiagnosticsResponse | null = null;

	onMount(async () => {
		const [envRes, logRes] = await Promise.allSettled([fetchSystemEnvironment(), fetchDiagnostics()]);
		if (envRes.status === 'fulfilled') env = envRes.value;
		else envError = envRes.reason instanceof Error ? envRes.reason.message : 'Failed to load the environment';
		if (logRes.status === 'fulfilled') logLevels = logRes.value.services;
		else logError = 'Failed to load log levels';
	});

	async function getReport(): Promise<string> {
		const current = env ?? (await fetchSystemEnvironment());
		health ??= await fetchSystemDiagnostics();
		return buildDeploymentReport(current, health, logLevels, new Date());
	}

	function yesNo(v: boolean | null): string {
		if (v === null) return 'unknown';
		return v ? 'yes' : 'no';
	}
</script>

<div class="stack stack-lg" data-page-section>
	<div class="stack stack-lg">
		<div class="settings-page-system-header">
			<h2 class="settings-page-section-title" data-page-section-title>System</h2>
			<CopyReportButton {getReport} />
		</div>

		{#if env}
			<p class="settings-page-system-summary" data-testid="system-summary">
				Version {env.version} | Host paths set: {yesNo(env.summary.host_paths_set)} | Transcode capable:
				{yesNo(env.summary.transcode_capable)} | GPUs: {env.summary.gpus.length ? env.summary.gpus.join(', ') : 'none'}
			</p>
		{:else if envError}
			<p class="field-error" data-testid="environment-error">{envError}</p>
		{/if}

		<section class="stack" data-testid="system-health-block" aria-labelledby="system-diagnostics-title">
			<h3 id="system-diagnostics-title" class="settings-page-section-title">Diagnostics</h3>
			<SystemHealth
				grouped
				onresult={(r) => {
					health = r;
				}}
			/>
		</section>

		{#if env}
			<EnvironmentSection groups={env.groups} {logLevels} {logError} />
			<ContainersSection containers={env.containers} />
		{:else if envError}
			<!-- Log levels do not depend on the environment endpoint. -->
			<EnvironmentSection groups={[{ name: 'Logging', vars: [] }]} {logLevels} {logError} />
		{/if}

		<!-- First-run walkthrough re-entry (setup spec 5.11) -->
		<section class="panel settings-page-setup-again" data-testid="run-setup-again">
			<div>
				<h3 class="settings-page-section-title">Setup walkthrough</h3>
				<p class="settings-page-setup-again-help">
					Walk through drives, keys and defaults again. Your current values are kept.
				</p>
			</div>
			<button type="button" class="btn" onclick={setup.run} disabled={setup.running}>
				{setup.running ? 'Opening...' : 'Run setup again'}
			</button>
		</section>
	</div>
</div>

<style>
	.settings-page-system-header {
		display: flex;
		flex-wrap: wrap;
		align-items: center;
		justify-content: space-between;
		gap: 0.75rem;
	}
	.settings-page-system-summary {
		font-size: 0.875rem;
		color: var(--color-text-muted);
	}
	.settings-page-section-title {
		font-size: 1.125rem;
		line-height: 1.75rem;
		font-weight: 600;
		color: var(--color-text);
	}
	.settings-page-setup-again {
		display: flex;
		flex-wrap: wrap;
		align-items: center;
		justify-content: space-between;
		gap: 0.75rem;
		padding: 1.25rem;
	}
	.settings-page-setup-again-help {
		font-size: 0.875rem;
		color: var(--color-text-muted);
	}
</style>
