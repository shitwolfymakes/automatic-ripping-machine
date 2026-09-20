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

	const cellClass = 'px-3 py-2 text-sm text-gray-700 dark:text-gray-300';
	const headClass =
		'px-3 py-2 text-left text-xs font-medium uppercase tracking-wider text-gray-500 dark:text-gray-400';
</script>

<section class="space-y-4">
	<div>
		<h2 class="text-lg font-semibold text-gray-900 dark:text-white">Diagnostics</h2>
		<p class="text-sm text-gray-500 dark:text-gray-400">
			Read-only view of each service's runtime log level.
		</p>
	</div>

	{#if error}
		<p class="text-sm text-red-600 dark:text-red-400" data-testid="diagnostics-error">{error}</p>
	{/if}

	{#if loading}
		<p class="py-8 text-center text-gray-400">Loading diagnostics...</p>
	{:else if services.length === 0}
		<p class="py-8 text-center text-gray-400">No services reported.</p>
	{:else}
		<div class="overflow-x-auto rounded-lg border border-primary/10 bg-surface dark:bg-surface-dark dark:border-primary/10">
			<table class="min-w-full divide-y divide-primary/10 dark:divide-primary/10">
				<thead>
					<tr>
						<th class={headClass}>Service</th>
						<th class={headClass}>Log level</th>
					</tr>
				</thead>
				<tbody class="divide-y divide-primary/5 dark:divide-primary/5">
					{#each services as s (s.name)}
						<tr data-testid="diagnostics-row">
							<td class={cellClass}>
								<span class="font-medium text-gray-900 dark:text-white">{s.name}</span>
							</td>
							<td class={cellClass}>
								<span
									class="inline-flex items-center rounded-full bg-primary/10 px-2 py-0.5 text-xs font-medium text-primary-text dark:text-primary-text-dark"
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

	<p class="text-xs text-gray-500 dark:text-gray-400">
		To change a level, set <code class="rounded bg-primary/5 px-1 py-0.5 text-primary-text dark:text-primary-text-dark">ARM_LOG_LEVEL</code>
		in <code class="rounded bg-primary/5 px-1 py-0.5 text-primary-text dark:text-primary-text-dark">.env</code> and restart the service.
	</p>
</section>
