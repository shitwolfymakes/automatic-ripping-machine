<script lang="ts">
	import { plural } from '$lib/utils/plural';
	// System health's list layout, used by Settings > System, with one row per
	// check and per storage path.
	import type { SystemDiagnosticsResponse } from '$lib/types/api.gen';
	import { formatDateTime } from '$lib/utils/format';
	import { checkDetail, checkLabel, healthTally, pathDetail, pathState } from '$lib/dashboard/system-health';
	import HealthCheckRow from './HealthCheckRow.svelte';

	let {
		result,
		error,
		loading,
		lastRun,
		scope,
		onrun
	}: {
		result: SystemDiagnosticsResponse | null;
		error: string | null;
		loading: boolean;
		lastRun: string | null;
		scope: 'all' | 'system';
		onrun: () => void;
	} = $props();
</script>

<div class="panel system-health-list-panel" data-testid="system-health">
	<div class="flex flex-wrap items-start justify-between gap-3">
		<div>
			<h3 class="system-health-list-title">System Health</h3>
			<p class="system-health-list-description">
				Configuration, storage paths, drives, MakeMKV key and decryption data, transcoder and ripper manager.
			</p>
		</div>
		<div class="flex items-center gap-3">
			{#if lastRun}
				<span class="system-health-list-last-run">Last run {formatDateTime(lastRun)}</span>
			{/if}
			<button
				type="button"
				onclick={onrun}
				disabled={loading}
				data-testid="system-health-run"
				class="btn system-health-list-run-btn"
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
				{tally.allOk ? 'All OK' : `${tally.issueCount} ${plural(tally.issueCount, 'issue')} found`}
			</span>
			<span class="panel-hint system-health-list-summary-count"
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
		<p class="system-health-list-placeholder mt-3">
			Click Run Checks to test the backend's configuration and connections.
		</p>
	{/if}
</div>

<style>
	/* the "Last run" note is text-xs text-gray-400 (a shade
	   fainter than panel-hint's --color-text-muted). */
	/* the panel is p-6 (1.5rem), not .panel's own p-4 (1rem) default. */
	.system-health-list-panel {
		padding: 1.5rem;
	}
	/* the button is a tinted fill (bg-primary/15, no border), not
	   .btn's default outlined look. */
	.system-health-list-run-btn {
		border: 0;
		background: var(--color-primary-tint-3);
		color: var(--color-primary-text);
	}
	.system-health-list-run-btn:hover {
		background: color-mix(in srgb, var(--color-primary) 25%, transparent);
	}
	/* text-base font-semibold text-gray-900 - a plain heading, not
	   panel-title's uppercase eyebrow look. */
	.system-health-list-title {
		font-size: 1rem;
		line-height: 1.5rem;
		font-weight: 600;
		color: var(--color-text);
	}
	.system-health-list-last-run {
		font-size: 0.75rem;
		line-height: 1rem;
		color: var(--color-text-faint);
	}
	.system-health-list-summary-count {
		margin-top: 0;
	}
	/* the header blurb and "Click Run Checks" placeholder are both text-sm
	   (0.875rem/1.25rem), not panel-hint's 0.75rem - but at different
	   shades: the blurb is text-gray-500 (muted), the placeholder
	   text-gray-400 (faint). */
	.system-health-list-description {
		font-size: 0.875rem;
		line-height: 1.25rem;
		color: var(--color-text-muted);
	}
	.system-health-list-placeholder {
		font-size: 0.875rem;
		line-height: 1.25rem;
		color: var(--color-text-faint);
	}
</style>
