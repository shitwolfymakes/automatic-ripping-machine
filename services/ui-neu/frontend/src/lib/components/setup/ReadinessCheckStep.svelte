<script lang="ts">
	import { onMount } from 'svelte';
	import {
		runPreflight,
		fixPreflight,
		type PreflightResult,
		type PreflightCheck,
		type PreflightPath,
	} from '$lib/api/system';

	const KEY_LABELS: Record<string, string> = {
		omdb_key: 'OMDb',
		tmdb_key: 'TMDb',
		tvdb_key: 'TVDB',
		makemkv_key: 'MakeMKV',
	};

	const KEY_SIGNUP_URLS: Record<string, string> = {
		omdb_key: 'https://www.omdbapi.com/apikey.aspx',
		tmdb_key: 'https://www.themoviedb.org/settings/api',
		tvdb_key: 'https://thetvdb.com/api-information',
	};

	let result = $state<PreflightResult | null>(null);
	let loading = $state(true);
	let fixing = $state(false);
	let error = $state<string | null>(null);

	type Status = 'pass' | 'warn' | 'fail';

	function checkStatus(c: PreflightCheck): Status {
		if (c.success) return 'pass';
		if (c.message === 'Not configured') return 'warn';
		return 'fail';
	}

	function pathStatus(p: PreflightPath): Status {
		if (!p.exists) return 'fail';
		if (!p.match) return 'fail';
		if (p.require_writable && !p.writable) return 'fail';
		return 'pass';
	}

	function chownCommand(p: PreflightPath, r: PreflightResult): string {
		const target = p.host_path || p.container_path;
		return `sudo chown -R ${r.arm_uid}:${r.arm_gid} ${target}`;
	}

	let fixableItems = $derived.by(() => {
		if (!result) return [] as string[];
		const items: string[] = [];
		for (const c of result.checks) {
			if (!c.success && c.fixable) items.push(c.name);
		}
		for (const p of result.paths) {
			if (pathStatus(p) === 'fail' && p.fixable) items.push(p.name);
		}
		return items;
	});

	async function load() {
		loading = true;
		error = null;
		try {
			result = await runPreflight();
		} catch {
			error = 'Failed to run readiness checks';
		} finally {
			loading = false;
		}
	}

	async function fix() {
		if (fixableItems.length === 0) return;
		fixing = true;
		try {
			result = await fixPreflight(fixableItems);
		} catch {
			error = 'Fix attempt failed';
		} finally {
			fixing = false;
		}
	}

	function copyToClipboard(text: string) {
		navigator.clipboard.writeText(text);
	}

	onMount(() => {
		load();
	});
</script>

<div class="stack stack-lg">
	<div class="readiness-step-header">
		<h2 class="readiness-step-title">Readiness Checks</h2>
		<p class="readiness-step-subtitle">
			Verifying API keys and path permissions.
		</p>
	</div>

	{#if loading}
		<div class="readiness-step-loading">
			<svg class="mx-auto h-8 w-8 spin readiness-step-spinner" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
				<circle class="spinner-track" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
				<path class="spinner-fill" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"></path>
			</svg>
			<p class="readiness-step-loading-text">Running checks...</p>
		</div>
	{:else if error && !result}
		<div class="alert alert-danger alert-lg">
			{error}
		</div>
	{:else if result}
		<!-- ARM Identity -->
		<div>
			<h3 class="eyebrow readiness-step-section-title">ARM Identity</h3>
			<div class="panel">
				<div class="cluster">
					<svg class="h-5 w-5 readiness-step-icon-ok" fill="currentColor" viewBox="0 0 20 20">
						<path fill-rule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clip-rule="evenodd" />
					</svg>
					<span class="readiness-step-identity">
						UID:{result.arm_uid} / GID:{result.arm_gid}
					</span>
				</div>
			</div>
		</div>

		<!-- API Keys -->
		<div>
			<h3 class="eyebrow readiness-step-section-title">API Keys</h3>
			<div class="stack stack-sm">
				{#each result.checks as check}
					{@const status = checkStatus(check)}
					<div class="panel">
						<div class="flex items-center justify-between">
							<div class="cluster">
								{#if status === 'pass'}
									<svg class="h-5 w-5 readiness-step-icon-ok" fill="currentColor" viewBox="0 0 20 20">
										<path fill-rule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clip-rule="evenodd" />
									</svg>
								{:else if status === 'warn'}
									<svg class="h-5 w-5 readiness-step-icon-warn" fill="currentColor" viewBox="0 0 20 20">
										<path fill-rule="evenodd" d="M8.257 3.099c.765-1.36 2.722-1.36 3.486 0l5.58 9.92c.75 1.334-.213 2.98-1.742 2.98H4.42c-1.53 0-2.493-1.646-1.743-2.98l5.58-9.92zM11 13a1 1 0 11-2 0 1 1 0 012 0zm-1-8a1 1 0 00-1 1v3a1 1 0 002 0V6a1 1 0 00-1-1z" clip-rule="evenodd" />
									</svg>
								{:else}
									<svg class="h-5 w-5 readiness-step-icon-fail" fill="currentColor" viewBox="0 0 20 20">
										<path fill-rule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z" clip-rule="evenodd" />
									</svg>
								{/if}
								<span class="readiness-step-check-name">
									{KEY_LABELS[check.name] ?? check.name}
								</span>
							</div>
							<div class="cluster">
								<span class="readiness-step-check-message" data-status={status}>
									{check.message}
								</span>
								{#if status === 'warn' && KEY_SIGNUP_URLS[check.name]}
									<a
										href={KEY_SIGNUP_URLS[check.name]}
										target="_blank"
										rel="noopener noreferrer"
										class="readiness-step-get-key"
									>
										Get key
									</a>
								{/if}
							</div>
						</div>
					</div>
				{/each}
			</div>
		</div>

		<!-- Paths & Permissions -->
		<div>
			<h3 class="eyebrow readiness-step-section-title">Paths &amp; Permissions</h3>
			<div class="stack stack-sm">
				{#each result.paths as path}
					{@const status = pathStatus(path)}
					<div class="panel">
						<div class="flex items-center justify-between">
							<div class="cluster">
								{#if status === 'pass'}
									<svg class="h-5 w-5 readiness-step-icon-ok" fill="currentColor" viewBox="0 0 20 20">
										<path fill-rule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clip-rule="evenodd" />
									</svg>
								{:else}
									<svg class="h-5 w-5 readiness-step-icon-fail" fill="currentColor" viewBox="0 0 20 20">
										<path fill-rule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z" clip-rule="evenodd" />
									</svg>
								{/if}
								<div>
									<span class="readiness-step-check-name">{path.name}</span>
									<div class="readiness-step-path-container">{path.container_path}</div>
								</div>
							</div>
							<div class="readiness-step-path-status">
								{#if status === 'pass'}
									<span class="readiness-step-check-message" data-status="pass">
										{#if !path.require_writable && !path.writable}Read-only{:else}OK{/if}
									</span>
								{:else}
									<span class="readiness-step-check-message" data-status="fail">
										{#if !path.exists}Missing{:else if !path.match}Owner mismatch{:else}Not writable{/if}
									</span>
								{/if}
							</div>
						</div>
						{#if status === 'fail' && !path.fixable}
							{@const cmd = chownCommand(path, result)}
							<div class="cluster readiness-step-chown-row">
								<code class="mono flex-1 truncate readiness-step-chown-cmd" title={cmd}>
									{cmd}
								</code>
								<button
									type="button"
									onclick={() => copyToClipboard(cmd)}
									class="btn btn-icon shrink-0"
									title="Copy command"
								>
									<svg class="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24" stroke-width="1.5">
										<path stroke-linecap="round" stroke-linejoin="round" d="M15.666 3.888A2.25 2.25 0 0013.5 2.25h-3c-1.03 0-1.9.693-2.166 1.638m7.332 0c.055.194.084.4.084.612v0a.75.75 0 01-.75.75H9.75a.75.75 0 01-.75-.75v0c0-.212.03-.418.084-.612m7.332 0c.646.049 1.288.11 1.927.184 1.1.128 1.907 1.077 1.907 2.185V19.5a2.25 2.25 0 01-2.25 2.25H6.75A2.25 2.25 0 014.5 19.5V6.257c0-1.108.806-2.057 1.907-2.185a48.208 48.208 0 011.927-.184" />
									</svg>
								</button>
							</div>
						{/if}
					</div>
				{/each}
			</div>
		</div>

		<!-- Action buttons -->
		<div class="cluster readiness-step-actions">
			<button
				type="button"
				onclick={load}
				disabled={loading}
				class="btn readiness-step-rerun-btn"
			>
				{loading ? 'Checking...' : 'Re-run Checks'}
			</button>
			{#if fixableItems.length > 0}
				<button
					type="button"
					onclick={fix}
					disabled={fixing}
					class="btn btn-primary"
				>
					{fixing ? 'Fixing...' : `Fix ${fixableItems.length} Issue${fixableItems.length === 1 ? '' : 's'}`}
				</button>
			{/if}
		</div>
	{/if}
</div>

<style>
	.readiness-step-header { text-align: center; }
	.readiness-step-title { font-size: 1.5rem; line-height: 2rem; font-weight: 700; color: var(--color-text); }
	.readiness-step-subtitle { margin-top: 0.5rem; color: var(--color-text-muted); }
	.readiness-step-loading { padding: 2rem 0; text-align: center; color: var(--color-text-faint); }
	.readiness-step-spinner { color: var(--color-primary); }
	.readiness-step-loading-text { margin-top: 0.75rem; }
	.readiness-step-section-title { margin-bottom: 0.5rem; }
	.readiness-step-identity, .readiness-step-check-name { font-size: 0.875rem; line-height: 1.25rem; font-weight: 500; color: var(--color-text); }
	.readiness-step-icon-ok { color: var(--color-success); }
	.readiness-step-icon-warn { color: var(--color-warning); }
	.readiness-step-icon-fail { color: var(--color-danger); }
	.readiness-step-check-message { font-size: 0.75rem; line-height: 1rem; }
	.readiness-step-check-message[data-status="pass"] { color: var(--color-success); }
	.readiness-step-check-message[data-status="warn"] { color: var(--color-on-warning-soft); }
	.readiness-step-check-message[data-status="fail"] { color: var(--color-danger); }
	/* the original was a soft warning-tone pill (bg-amber-100 text-amber-700),
	   not a solid badge fill - no shared block matches this shape exactly,
	   so it stays a local class using the warning-soft/on-warning-soft pair */
	.readiness-step-get-key { border-radius: var(--radius-md); padding: 0.125rem 0.5rem; font-size: 0.75rem; line-height: 1rem; font-weight: 500; background: var(--color-warning-soft); color: var(--color-on-warning-soft); }
	.readiness-step-get-key:hover { background: color-mix(in srgb, var(--color-warning-soft) 60%, var(--color-warning)); }
	.readiness-step-path-container { font-size: 0.75rem; line-height: 1rem; color: var(--color-text-faint); }
	.readiness-step-path-status { text-align: right; }
	.readiness-step-chown-row { margin-top: 0.5rem; }
	.readiness-step-chown-cmd { border-radius: var(--radius-sm); padding: 0.25rem 0.5rem; font-size: 0.75rem; line-height: 1rem; color: var(--color-text-secondary); background: var(--color-primary-tint-2); }
	.readiness-step-actions { justify-content: center; }
	/* original was a tinted-fill button (bg-primary/15, no border) */
	.readiness-step-rerun-btn { border: 0; background: var(--color-primary-tint-3); color: var(--color-primary-text); }
	.readiness-step-rerun-btn:hover { background: color-mix(in srgb, var(--color-primary-tint-3) 70%, var(--color-primary)); }
</style>
