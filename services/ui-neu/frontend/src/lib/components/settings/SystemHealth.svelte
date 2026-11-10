<script lang="ts">
	import { onMount } from 'svelte';
	import { fetchSystemDiagnostics } from '$lib/api/system';
	import { fetchResources } from '$lib/api/resources';
	import type { SystemDiagnosticsResponse, StorageRoot } from '$lib/types/api.gen';
	import { formatDateTime } from '$lib/utils/format';
	import {
		checkDetail,
		checkLabel,
		healthTally,
		otherChecks,
		pathDetail,
		pathState,
		serviceChecks
	} from '$lib/utils/system-health';
	import Glyph from '$lib/components/Glyph.svelte';
	import HealthCheckRow from './HealthCheckRow.svelte';
	import ServiceItem from './ServiceItem.svelte';
	import StoragePathItem from './StoragePathItem.svelte';

	// Settings > System and the setup walkthrough's System check share this.
	// `grouped`: Storage + Services panels with fix commands (setup spec §5.3).
	// `scope="system"`: only what the System check step is about; drives and
	// the MakeMKV key are later steps. `autorun`: check on mount.
	let {
		autorun = false,
		grouped = false,
		scope = 'all',
		onresult
	}: {
		autorun?: boolean;
		grouped?: boolean;
		scope?: 'all' | 'system';
		onresult?: (r: SystemDiagnosticsResponse) => void;
	} = $props();

	let result = $state<SystemDiagnosticsResponse | null>(null);
	let loading = $state(false);
	let error = $state<string | null>(null);
	let lastRun = $state<string | null>(null);

	let storage = $state<StorageRoot[] | null>(null);

	async function runChecks(): Promise<void> {
		loading = true;
		error = null;
		try {
			result = await fetchSystemDiagnostics();
			lastRun = new Date().toISOString();
			onresult?.(result);
		} catch (e) {
			error = e instanceof Error ? e.message : 'Health checks failed';
		} finally {
			loading = false;
		}
		if (grouped) storage = await loadStorage();
	}

	/** The storage roots for the free-space chips, or null when the
	 * lookup fails. */
	async function loadStorage(): Promise<StorageRoot[] | null> {
		try {
			return (await fetchResources()).storage;
		} catch {
			return null;
		}
	}

	onMount(() => {
		if (autorun) void runChecks();
	});
</script>

{#if grouped}
	<div class="stack stack-lg" data-testid="system-health">
		<div class="flex flex-wrap items-center justify-between gap-3">
			<span class="system-health-last-run flex items-center gap-1.5">
				<Glyph name="clock" />
				{lastRun ? `Checked ${formatDateTime(lastRun)}` : 'Not checked yet'}
			</span>
			<button type="button" onclick={runChecks} disabled={loading} data-testid="system-health-run" class="btn">
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
						<strong>{tally.problemCount} problem{tally.problemCount === 1 ? '' : 's'} to fix on the server</strong><br
						/>
						These come from .env and docker-compose, so the fix happens on the server, not here.
					</span>
				</div>
			{/if}

			<section class="panel system-health-group" aria-labelledby="system-health-storage">
				<h3 id="system-health-storage" class="system-health-title">Storage</h3>
				<p class="system-health-description">Folders from docker-compose. ARM needs to write to all three.</p>
				<div class="stack mt-3">
					{#each result.paths as p (p.name)}
						<StoragePathItem folder={p} {storage} />
					{/each}
				</div>
			</section>

			<section class="panel system-health-group" aria-labelledby="system-health-services">
				<h3 id="system-health-services" class="system-health-title">Services</h3>
				<p class="system-health-description">What ARM can start on this server.</p>
				<div class="stack mt-3">
					{#each services as c (c.name)}
						<ServiceItem check={c} />
					{/each}
				</div>
			</section>

			{#if others.length > 0 && (scope === 'all' || others.some((c) => c.status !== 'ok'))}
				<section class="panel system-health-group" aria-labelledby="system-health-other">
					<h3 id="system-health-other" class="system-health-title">Other checks</h3>
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
			<p class="system-health-placeholder">Checking the server...</p>
		{/if}
	</div>
{:else}
	<div class="panel system-health-panel" data-testid="system-health">
		<div class="flex flex-wrap items-start justify-between gap-3">
			<div>
				<h3 class="system-health-title">System Health</h3>
				<p class="system-health-description">
					Configuration, storage paths, drives, MakeMKV key and decryption data, transcoder and ripper manager.
				</p>
			</div>
			<div class="flex items-center gap-3">
				{#if lastRun}
					<span class="system-health-last-run">Last run {formatDateTime(lastRun)}</span>
				{/if}
				<button
					type="button"
					onclick={runChecks}
					disabled={loading}
					data-testid="system-health-run"
					class="btn system-health-run-btn"
				>
					{loading ? 'Running...' : 'Run Checks'}
				</button>
			</div>
		</div>

		{#if error}
			<p class="field-error mt-3" data-testid="system-health-error">{error}</p>
		{:else if result}
			{@const tally = healthTally(result, scope)}
			<div
				class="alert {tally.allOk ? 'alert-success' : 'alert-warning'} mt-4 flex items-center gap-3"
				data-testid="system-health-summary"
			>
				<span class="alert-title">
					{tally.allOk ? 'All OK' : `${tally.issueCount} issue${tally.issueCount === 1 ? '' : 's'} found`}
				</span>
				<span class="panel-hint system-health-summary-count"
					>{result.checks.length} checks, {result.paths.length} paths</span
				>
			</div>

			<ul class="mt-3">
				{#each result.checks as check (check.name)}
					<HealthCheckRow testid="system-health-check" status={check.status} label={checkLabel(check.name)}
						>{checkDetail(check)}</HealthCheckRow
					>
				{/each}
				{#each result.paths as p (p.name)}
					<HealthCheckRow testid="system-health-path" status={pathState(p)} label={p.name}
						><code class="mono">{p.path}</code>, {pathDetail(p)}</HealthCheckRow
					>
				{/each}
			</ul>
		{:else}
			<p class="system-health-placeholder mt-3">
				Click Run Checks to test the backend's configuration and connections.
			</p>
		{/if}
	</div>
{/if}

<style>
	/* the original "Last run" note was text-xs text-gray-400 (a shade
	   fainter than panel-hint's --color-text-muted). */
	/* the original panel was p-6 (1.5rem), not .panel's own p-4 (1rem) default. */
	.system-health-panel {
		padding: 1.5rem;
	}
	/* the original button was a tinted fill (bg-primary/15, no border), not
	   .btn's default outlined look. */
	.system-health-run-btn {
		border: 0;
		background: var(--color-primary-tint-3);
		color: var(--color-primary-text);
	}
	.system-health-run-btn:hover {
		background: color-mix(in srgb, var(--color-primary) 25%, transparent);
	}
	/* text-base font-semibold text-gray-900 - a plain heading, not
	   panel-title's uppercase eyebrow look. */
	.system-health-title {
		font-size: 1rem;
		line-height: 1.5rem;
		font-weight: 600;
		color: var(--color-text);
	}
	.system-health-last-run {
		font-size: 0.75rem;
		line-height: 1rem;
		color: var(--color-text-faint);
	}
	.system-health-summary-count {
		margin-top: 0;
	}
	/* the header blurb and "Click Run Checks" placeholder were both text-sm
	   (0.875rem/1.25rem), not panel-hint's 0.75rem - but at different
	   shades: the blurb was text-gray-500 (muted), the placeholder
	   text-gray-400 (faint). */
	.system-health-description {
		font-size: 0.875rem;
		line-height: 1.25rem;
		color: var(--color-text-muted);
	}
	.system-health-group {
		padding: 1.25rem;
	}
	.system-health-placeholder {
		font-size: 0.875rem;
		line-height: 1.25rem;
		color: var(--color-text-faint);
	}
</style>
