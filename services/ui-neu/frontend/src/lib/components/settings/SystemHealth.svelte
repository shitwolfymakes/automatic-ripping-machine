<script lang="ts">
	import { fetchSystemDiagnostics } from '$lib/api/system';
	import type { SystemDiagnosticsResponse, SystemDiagnosticCheck, PathStatus } from '$lib/types/api.gen';
	import { formatDateTime } from '$lib/utils/format';

	// Operator-facing names for the backend's check keys.
	const CHECK_LABELS: Record<string, string> = {
		config: 'Configuration',
		MEDIA_ROOT: 'Media root',
		RAW_ROOT: 'Raw root',
		LOG_DIR: 'Log directory',
		drives: 'Drives',
		makemkv_key: 'MakeMKV key',
		community_keydb: 'Community keydb',
		makemkv_sdf: 'MakeMKV SDF',
		transcoder: 'Transcoder',
		ripper_manager: 'Ripper manager'
	};
	const label = (name: string) => CHECK_LABELS[name] ?? name;

	let result = $state<SystemDiagnosticsResponse | null>(null);
	let loading = $state(false);
	let error = $state<string | null>(null);
	let lastRun = $state<string | null>(null);

	const issues = $derived(result ? result.checks.filter((c) => c.status !== 'ok') : []);
	const pathIssues = $derived(result ? result.paths.filter((p) => !p.exists || !p.writable) : []);
	const allOk = $derived(result !== null && issues.length === 0 && pathIssues.length === 0);

	async function runChecks(): Promise<void> {
		loading = true;
		error = null;
		try {
			result = await fetchSystemDiagnostics();
			lastRun = new Date().toISOString();
		} catch (e) {
			error = e instanceof Error ? e.message : 'Health checks failed';
		} finally {
			loading = false;
		}
	}

	function pathState(p: PathStatus): SystemDiagnosticCheck['status'] {
		if (!p.exists) return 'error';
		if (!p.writable) return 'warning';
		return 'ok';
	}
	function pathDetail(p: PathStatus): string {
		if (!p.exists) return 'missing';
		if (!p.writable) return 'not writable';
		return 'writable';
	}
</script>

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
		<div
			class="alert {allOk ? 'alert-success' : 'alert-warning'} mt-4 flex items-center gap-3"
			data-testid="system-health-summary"
		>
			<span class="alert-title">
				{allOk ? 'All OK' : `${issues.length + pathIssues.length} issue${issues.length + pathIssues.length === 1 ? '' : 's'} found`}
			</span>
			<span class="panel-hint system-health-summary-count">{result.checks.length} checks, {result.paths.length} paths</span>
		</div>

		<ul class="mt-3">
			{#each result.checks as check (check.name)}
				<li class="list-row list-row-compact system-health-row" data-testid="system-health-check" data-status={check.status}>
					<span class="status-dot" data-status={check.status}></span>
					<span class="system-health-row-label">{label(check.name)}</span>
					<span class="system-health-row-detail">{check.detail ?? (check.status === 'ok' ? 'OK' : check.status)}</span>
				</li>
			{/each}
			{#each result.paths as p (p.name)}
				{@const st = pathState(p)}
				<li class="list-row list-row-compact system-health-row" data-testid="system-health-path" data-status={st}>
					<span class="status-dot" data-status={st}></span>
					<span class="system-health-row-label">{p.name}</span>
					<span class="system-health-row-detail"><code class="mono">{p.path}</code>, {pathDetail(p)}</span>
				</li>
			{/each}
		</ul>
	{:else}
		<p class="system-health-placeholder mt-3">Click Run Checks to test the backend's configuration and connections.</p>
	{/if}
</div>

<style>
	/* the original "Last run" note was text-xs text-gray-400 (a shade
	   fainter than panel-hint's --color-text-muted). */
	/* the original panel was p-6 (1.5rem), not .panel's own p-4 (1rem) default. */
	.system-health-panel { padding: 1.5rem; }
	/* the original button was a tinted fill (bg-primary/15, no border), not
	   .btn's default outlined look. */
	.system-health-run-btn { border: 0; background: var(--color-primary-tint-3); color: var(--color-primary-text); }
	.system-health-run-btn:hover { background: color-mix(in srgb, var(--color-primary) 25%, transparent); }
	/* text-base font-semibold text-gray-900 - a plain heading, not
	   panel-title's uppercase eyebrow look. */
	.system-health-title { font-size: 1rem; line-height: 1.5rem; font-weight: 600; color: var(--color-text); }
	.system-health-last-run { font-size: 0.75rem; line-height: 1rem; color: var(--color-text-faint); }
	/* list-row is a grid whose column template the owning list sets; these
	   rows are a simple inline label/status/detail line, not a data grid. */
	.system-health-row { display: flex; align-items: flex-start; gap: 0.5rem; cursor: default; }
	.system-health-row-label { width: 10rem; flex-shrink: 0; color: var(--color-text); font-size: 0.875rem; }
	/* the original detail text inherited the list's own text-sm (0.875rem)
	   context, not panel-hint's smaller 0.75rem. */
	.system-health-row-detail { font-size: 0.875rem; line-height: 1.25rem; color: var(--color-text-muted); }
	.system-health-summary-count { margin-top: 0; }
	/* the header blurb and "Click Run Checks" placeholder were both text-sm
	   (0.875rem/1.25rem), not panel-hint's 0.75rem - but at different
	   shades: the blurb was text-gray-500 (muted), the placeholder
	   text-gray-400 (faint). */
	.system-health-description { font-size: 0.875rem; line-height: 1.25rem; color: var(--color-text-muted); }
	.system-health-placeholder { font-size: 0.875rem; line-height: 1.25rem; color: var(--color-text-faint); }
</style>
