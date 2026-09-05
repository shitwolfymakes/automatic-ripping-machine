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

	function rowClass(status: string): string {
		if (status === 'ok') return 'text-green-600 dark:text-green-400';
		if (status === 'warning') return 'text-amber-600 dark:text-amber-400';
		return 'text-red-600 dark:text-red-400';
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

<div class="rounded-lg border border-primary/20 bg-surface p-6 shadow-xs dark:border-primary/20 dark:bg-surface-dark" data-testid="system-health">
	<div class="flex flex-wrap items-start justify-between gap-3">
		<div>
			<h3 class="text-base font-semibold text-gray-900 dark:text-white">System Health</h3>
			<p class="text-sm text-gray-500 dark:text-gray-400">
				Configuration, storage paths, drives, MakeMKV key and decryption data, transcoder and ripper manager.
			</p>
		</div>
		<div class="flex items-center gap-3">
			{#if lastRun}
				<span class="text-xs text-gray-400 dark:text-gray-500">Last run {formatDateTime(lastRun)}</span>
			{/if}
			<button
				type="button"
				onclick={runChecks}
				disabled={loading}
				data-testid="system-health-run"
				class="rounded-lg bg-primary/15 px-4 py-2 text-sm font-medium text-primary-text transition-colors hover:bg-primary/25 disabled:opacity-50 dark:text-primary-text-dark dark:hover:bg-primary/30"
			>
				{loading ? 'Running...' : 'Run Checks'}
			</button>
		</div>
	</div>

	{#if error}
		<p class="mt-3 text-sm text-red-600 dark:text-red-400" data-testid="system-health-error">{error}</p>
	{:else if result}
		<div
			class="mt-4 flex items-center gap-3 rounded-lg border px-3 py-2 text-xs {allOk ? 'border-green-500/15 bg-green-500/5' : 'border-amber-500/15 bg-amber-500/5'}"
			data-testid="system-health-summary"
		>
			<span class="font-medium {allOk ? 'text-green-600 dark:text-green-400' : 'text-amber-600 dark:text-amber-400'}">
				{allOk ? 'All OK' : `${issues.length + pathIssues.length} issue${issues.length + pathIssues.length === 1 ? '' : 's'} found`}
			</span>
			<span class="text-gray-500 dark:text-gray-400">{result.checks.length} checks, {result.paths.length} paths</span>
		</div>

		<ul class="mt-3 divide-y divide-primary/10 text-sm dark:divide-primary/15">
			{#each result.checks as check (check.name)}
				<li class="flex items-start gap-2 py-1.5" data-testid="system-health-check" data-status={check.status}>
					{#if check.status === 'ok'}
						<svg class="mt-0.5 h-4 w-4 shrink-0 {rowClass(check.status)}" fill="currentColor" viewBox="0 0 20 20">
							<path fill-rule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clip-rule="evenodd" />
						</svg>
					{:else if check.status === 'warning'}
						<svg class="mt-0.5 h-4 w-4 shrink-0 {rowClass(check.status)}" fill="none" stroke="currentColor" viewBox="0 0 24 24">
							<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-2.5L13.732 4c-.77-.833-1.964-.833-2.732 0L4.082 16.5c-.77.833.192 2.5 1.732 2.5z" />
						</svg>
					{:else}
						<svg class="mt-0.5 h-4 w-4 shrink-0 {rowClass(check.status)}" fill="currentColor" viewBox="0 0 20 20">
							<path fill-rule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z" clip-rule="evenodd" />
						</svg>
					{/if}
					<span class="w-40 shrink-0 text-gray-900 dark:text-white">{label(check.name)}</span>
					<span class="text-gray-500 dark:text-gray-400">{check.detail ?? (check.status === 'ok' ? 'OK' : check.status)}</span>
				</li>
			{/each}
			{#each result.paths as p (p.name)}
				{@const st = pathState(p)}
				<li class="flex items-start gap-2 py-1.5" data-testid="system-health-path" data-status={st}>
					<span class="mt-0.5 h-4 w-4 shrink-0 text-center text-xs font-semibold {rowClass(st)}">{st === 'ok' ? '' : '!'}</span>
					<span class="w-40 shrink-0 text-gray-900 dark:text-white">{p.name}</span>
					<span class="text-gray-500 dark:text-gray-400"><code class="text-xs">{p.path}</code>, {pathDetail(p)}</span>
				</li>
			{/each}
		</ul>
	{:else}
		<p class="mt-3 text-sm text-gray-400 dark:text-gray-500">Click Run Checks to test the backend's configuration and connections.</p>
	{/if}
</div>
