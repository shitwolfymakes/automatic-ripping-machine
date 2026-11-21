<script lang="ts">
	import type { ContainerView } from '$lib/types/api.gen';

	interface Props {
		containers: ContainerView[];
	}

	let { containers }: Props = $props();
</script>

{#if containers.length > 0}
	<section class="stack" data-testid="containers-section">
		<h3 class="containers-section-title">Containers</h3>
		{#each containers as c (c.kind + c.label)}
			<details class="panel containers-section-item" data-testid="container-{c.label}">
				<summary class="containers-section-summary">
					<span class="containers-section-name">{c.label}</span>
					<span class="badge">{c.kind}</span>
					<span class="containers-section-state">{c.state ?? 'unknown'}</span>
				</summary>
				<dl class="containers-section-detail">
					<dt>Image</dt>
					<dd class="mono">{c.image}</dd>
					<dt>Network</dt>
					<dd class="mono">{c.network ?? 'none'}</dd>
					<dt>Docker host</dt>
					<dd class="mono">{c.docker_host ?? 'local'}</dd>
					<dt>Mounts</dt>
					<dd>
						{#each c.mounts as m (m.host + m.container)}
							<div class="mono">{m.host} : {m.container} ({m.mode})</div>
						{:else}
							none
						{/each}
					</dd>
					<dt>Devices</dt>
					<dd>
						{#each c.devices as d (d)}
							<div class="mono">{d}</div>
						{:else}
							none
						{/each}
					</dd>
					<dt>Environment</dt>
					<dd>
						{#each c.env as e (e.key)}
							<div class="mono">
								{e.key}={e.secret ? '<secret>' : (e.value ?? '')}
							</div>
						{:else}
							none
						{/each}
					</dd>
				</dl>
			</details>
		{/each}
	</section>
{/if}

<style>
	.containers-section-title {
		font-size: 1.125rem;
		line-height: 1.75rem;
		font-weight: 600;
		color: var(--color-text);
	}
	.containers-section-item {
		padding: 0.75rem 1rem;
	}
	.containers-section-summary {
		display: flex;
		align-items: center;
		gap: 0.5rem;
		cursor: pointer;
	}
	.containers-section-name {
		font-weight: 600;
		color: var(--color-text);
	}
	.containers-section-state {
		font-size: 0.75rem;
		color: var(--color-text-muted);
	}
	.containers-section-detail {
		display: grid;
		grid-template-columns: max-content 1fr;
		gap: 0.25rem 1rem;
		margin-top: 0.75rem;
		font-size: 0.875rem;
	}
	.containers-section-detail dt {
		color: var(--color-text-muted);
	}
	.containers-section-detail dd {
		word-break: break-all;
	}
</style>
