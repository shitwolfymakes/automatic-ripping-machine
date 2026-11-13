<script lang="ts">
	import { plural } from '$lib/utils/plural';
	// System health's grouped layout, used by the setup walkthrough's System
	// step, with storage and services as cards and fix commands for what fails.
	import type { SystemDiagnosticsResponse, StorageRoot } from '$lib/types/api.gen';
	import { formatDateTime } from '$lib/utils/format';
	import { checkDetail, checkLabel, healthTally, otherChecks, serviceChecks } from '$lib/utils/system-health';
	import Glyph from '$lib/components/Glyph.svelte';
	import HealthCheckRow from './HealthCheckRow.svelte';
	import ServiceItem from './ServiceItem.svelte';
	import StoragePathItem from './StoragePathItem.svelte';

	let {
		result,
		error,
		loading,
		lastRun,
		storage,
		scope,
		onrun
	}: {
		result: SystemDiagnosticsResponse | null;
		error: string | null;
		loading: boolean;
		lastRun: string | null;
		storage: readonly StorageRoot[] | null;
		scope: 'all' | 'system';
		onrun: () => void;
	} = $props();
</script>

<div class="stack stack-lg" data-testid="system-health">
	<div class="flex flex-wrap items-center justify-between gap-3">
		<span class="system-health-grouped-last-run flex items-center gap-1.5">
			<Glyph name="clock" />
			{lastRun ? `Checked ${formatDateTime(lastRun)}` : 'Not checked yet'}
		</span>
		<button type="button" onclick={onrun} disabled={loading} data-testid="system-health-run" class="btn">
			<Glyph name="refresh" class={loading ? 'spin' : ''} />
			{loading ? 'Checking...' : 'Check again'}
		</button>
	</div>

	{#if error}
		<p class="alert alert-danger" data-testid="system-health-error">{error}</p>
	{:else if result}
		{@const tally = healthTally(result, scope)}
		{@const services = serviceChecks(result.checks)}
		{@const others = otherChecks(result.checks, scope)}
		{#if tally.allOk}
			<div class="alert alert-success flex items-center gap-2" data-testid="system-health-summary">
				<Glyph name="check-circle" />
				<span><strong>Everything checks out.</strong> Storage and services are ready.</span>
			</div>
		{:else}
			<div class="alert alert-danger flex items-start gap-2" data-testid="system-health-summary" role="alert">
				<Glyph name="x-circle" class="mt-0.5" />
				<span>
					<strong>{tally.problemCount} {plural(tally.problemCount, 'problem')} to fix on the server</strong><br />
					These come from .env and docker-compose, so the fix happens on the server, not here.
				</span>
			</div>
		{/if}

		<section class="panel system-health-grouped-section" aria-labelledby="system-health-storage">
			<h3 id="system-health-storage" class="system-health-grouped-title">Storage</h3>
			<p class="system-health-grouped-description">Folders from docker-compose. ARM needs to write to all three.</p>
			<div class="stack mt-3">
				{#each result.paths as p (p.name)}
					<StoragePathItem folder={p} {storage} />
				{/each}
			</div>
		</section>

		<section class="panel system-health-grouped-section" aria-labelledby="system-health-services">
			<h3 id="system-health-services" class="system-health-grouped-title">Services</h3>
			<p class="system-health-grouped-description">What ARM can start on this server.</p>
			<div class="stack mt-3">
				{#each services as c (c.name)}
					<ServiceItem check={c} />
				{/each}
			</div>
		</section>

		{#if others.length > 0 && (scope === 'all' || others.some((c) => c.status !== 'ok'))}
			<section class="panel system-health-grouped-section" aria-labelledby="system-health-other">
				<h3 id="system-health-other" class="system-health-grouped-title">Other checks</h3>
				<ul class="mt-2">
					{#each others as check (check.name)}
						<HealthCheckRow testid="system-health-check" status={check.status} label={checkLabel(check.name)}
							>{checkDetail(check)}</HealthCheckRow
						>
					{/each}
				</ul>
			</section>
		{/if}
	{:else if loading}
		<p class="system-health-grouped-placeholder">Checking the server...</p>
	{/if}
</div>

<style>
	/* The title, last-run, description and placeholder rules match
	   SystemHealthList's. */
	.system-health-grouped-title {
		font-size: 1rem;
		line-height: 1.5rem;
		font-weight: 600;
		color: var(--color-text);
	}
	.system-health-grouped-last-run {
		font-size: 0.75rem;
		line-height: 1rem;
		color: var(--color-text-faint);
	}
	.system-health-grouped-description {
		font-size: 0.875rem;
		line-height: 1.25rem;
		color: var(--color-text-muted);
	}
	.system-health-grouped-placeholder {
		font-size: 0.875rem;
		line-height: 1.25rem;
		color: var(--color-text-faint);
	}
	.system-health-grouped-section {
		padding: 1.25rem;
	}
</style>
