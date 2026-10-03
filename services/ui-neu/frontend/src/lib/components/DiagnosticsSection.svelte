<script lang="ts">
	// Ported from services/ui/src/views/Diagnostics.vue — a read-only Service /
	// Log-level table from GET /api/diagnostics. Self-loading section (matches
	// the Rip/Transcode/Sessions settings sections, minus CRUD). Log levels are
	// .env-configured (ARM_LOG_LEVEL); there is no write path.
	import { onMount } from 'svelte';
	import { fetchDiagnostics } from '$lib/api/diagnostics';
	import type { DiagnosticsServiceView } from '$lib/types/api.gen';

	let services = $state<DiagnosticsServiceView[]>([]);
	let loading = $state(true);
	let error = $state<string | null>(null);

	async function load(): Promise<void> {
		loading = true;
		error = null;
		try {
			const resp = await fetchDiagnostics();
			services = resp.services;
		} catch (e) {
			error = e instanceof Error ? e.message : 'Failed to load diagnostics';
		} finally {
			loading = false;
		}
	}

	onMount(load);
</script>

<section class="stack">
	<div>
		<h2 class="diagnostics-section-title">Diagnostics</h2>
		<p class="diagnostics-section-description">
			Read-only view of each service's runtime log level.
		</p>
	</div>

	{#if error}
		<p class="field-error" data-testid="diagnostics-error">{error}</p>
	{/if}

	{#if loading}
		<p class="diagnostics-section-empty">Loading diagnostics...</p>
	{:else if services.length === 0}
		<p class="diagnostics-section-empty">No services reported.</p>
	{:else}
		<div class="overflow-x-auto diagnostics-section-table-wrap">
			<table class="table">
				<thead>
					<tr>
						<th class="table-header">Service</th>
						<th class="table-header">Log level</th>
					</tr>
				</thead>
				<tbody>
					{#each services as s (s.name)}
						<tr class="table-row" data-testid="diagnostics-row">
							<td class="table-cell">
								<span class="diagnostics-section-name">{s.name}</span>
							</td>
							<td class="table-cell">
								<span
									class="badge"
									data-testid="diag-level-{s.name}"
								>
									{s.log_level}
								</span>
							</td>
						</tr>
					{/each}
				</tbody>
			</table>
		</div>
	{/if}

	<p class="panel-hint">
		To change a level, set <code class="mono diagnostics-section-code">ARM_LOG_LEVEL</code>
		in <code class="mono diagnostics-section-code">.env</code> and restart the service.
	</p>
</section>

<style>
	.diagnostics-section-title { font-size: 1.125rem; line-height: 1.75rem; font-weight: 600; color: var(--color-text); }
	/* the original description was text-sm (0.875rem/1.25rem), not
	   panel-hint's 0.75rem - panel-hint is sized for a note under a form
	   control, a visibly smaller role. */
	.diagnostics-section-description { font-size: 0.875rem; line-height: 1.25rem; color: var(--color-text-muted); }
	.diagnostics-section-empty { padding: 2rem 0; text-align: center; color: var(--color-text-faint); }
	.diagnostics-section-table-wrap { border: 1px solid var(--color-border); border-radius: var(--radius-lg); background: var(--color-surface); }
	.diagnostics-section-name { font-weight: 500; color: var(--color-text); }
	.diagnostics-section-code { font-size: 0.7rem; padding: 0 0.25rem; border-radius: var(--radius-sm); background: var(--color-primary-tint-2); color: var(--color-primary-text); }
</style>
