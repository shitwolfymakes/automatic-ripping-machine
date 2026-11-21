<script lang="ts">
	import type { DiagnosticsServiceView, EnvGroupView } from '$lib/types/api.gen';

	interface Props {
		groups: EnvGroupView[];
		logLevels: DiagnosticsServiceView[];
	}

	let { groups, logLevels }: Props = $props();

	// Groups start open; a name in this set has been collapsed.
	let collapsed = $state<Record<string, boolean>>({});

	function toggle(name: string): void {
		collapsed[name] = !collapsed[name];
	}

	function fieldHref(tab: string, key: string | null): string {
		return key ? `#${tab}/${key}` : `#${tab}`;
	}
</script>

<section class="stack" data-testid="environment-section">
	<h3 class="environment-section-title">Environment</h3>
	{#each groups as g (g.name)}
		<div class="panel environment-section-group">
			<button
				type="button"
				class="environment-section-toggle"
				aria-expanded={!collapsed[g.name]}
				onclick={() => toggle(g.name)}
			>
				<span>{g.name}</span>
				<span class="environment-section-count">{g.vars.length}</span>
			</button>
			{#if !collapsed[g.name]}
				<div class="overflow-x-auto">
					<table class="table">
						<thead>
							<tr>
								<th class="table-header">Variable</th>
								<th class="table-header">Value</th>
								<th class="table-header">Source</th>
							</tr>
						</thead>
						<tbody>
							{#each g.vars as v (v.key)}
								<tr class="table-row" data-testid="env-{v.key}">
									<td class="table-cell"><span class="mono">{v.key}</span></td>
									<td class="table-cell">
										{#if v.secret}
											<span class="badge">{v.is_set ? 'set' : 'not set'}</span>
										{:else}
											<span class="mono environment-section-value">{v.value ?? ''}</span>
										{/if}
										{#if v.effective}
											<a class="environment-section-inuse" href={fieldHref(v.effective.tab, v.effective.setting_key)}
												>in use: {v.effective.value} (Settings, {v.effective.tab})</a
											>
										{/if}
									</td>
									<td class="table-cell">{v.source}</td>
								</tr>
							{/each}
							{#if g.name === 'Logging'}
								{#each logLevels as s (s.name)}
									<tr class="table-row" data-testid="diagnostics-row">
										<td class="table-cell"><span class="mono">{s.name} log level</span></td>
										<td class="table-cell">
											<span class="badge" data-testid="diag-level-{s.name}">{s.log_level}</span>
										</td>
										<td class="table-cell">runtime</td>
									</tr>
								{/each}
							{/if}
						</tbody>
					</table>
				</div>
			{/if}
		</div>
	{/each}
	<p class="panel-hint">
		Read-only. To change a log level, set <code class="mono">ARM_LOG_LEVEL</code> in
		<code class="mono">.env</code> and restart the service.
	</p>
</section>

<style>
	.environment-section-title {
		font-size: 1.125rem;
		line-height: 1.75rem;
		font-weight: 600;
		color: var(--color-text);
	}
	.environment-section-group {
		padding: 0;
		overflow: hidden;
	}
	.environment-section-toggle {
		display: flex;
		width: 100%;
		align-items: center;
		justify-content: space-between;
		padding: 0.75rem 1rem;
		font-weight: 600;
		color: var(--color-text);
		background: transparent;
		border: 0;
		cursor: pointer;
	}
	.environment-section-count {
		font-size: 0.75rem;
		color: var(--color-text-muted);
	}
	.environment-section-value {
		word-break: break-all;
	}
	.environment-section-inuse {
		display: block;
		font-size: 0.75rem;
		color: var(--color-primary-text);
	}
</style>
