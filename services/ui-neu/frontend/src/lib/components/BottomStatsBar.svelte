<script lang="ts">
	import { onMount } from 'svelte';
	import { resources, startResources, stopResources } from '$lib/stores/resources.svelte';
	import { barColor, filesHref } from '$lib/utils/resource-bars';

	onMount(() => {
		startResources();
		return () => stopResources();
	});
</script>

<!-- Fixed bottom bar, hidden below lg (1024px) — matches neu placement. -->
<div data-testid="bottom-stats-bar" class="stats-bar hidden h-10 items-center gap-3 lg:flex 2xl:hidden">
	<!-- CPU -->
	<div class="stats-bar-group flex items-center gap-2">
		<span class="shrink-0">CPU</span>
		<div class="progress progress-sm stats-bar-track">
			<div class="progress-track">
				<div class="progress-fill" data-bar={barColor($resources.cpu_percent, 'cpu')} style:--progress="{Math.min(100, $resources.cpu_percent)}%"></div>
			</div>
		</div>
		<span class="stats-bar-slot stats-bar-slot-pct shrink-0">{$resources.cpu_percent.toFixed(0)}%</span>
	</div>

	<div class="stats-bar-divider shrink-0"></div>

	<!-- Memory -->
	<div class="stats-bar-group flex items-center gap-2">
		<span class="shrink-0">Mem</span>
		<div class="progress progress-sm stats-bar-track">
			<div class="progress-track">
				<div class="progress-fill" data-bar={barColor($resources.memory.percent, 'mem')} style:--progress="{Math.min(100, $resources.memory.percent)}%"></div>
			</div>
		</div>
		<span class="stats-bar-slot stats-bar-slot-mem shrink-0 whitespace-nowrap">{$resources.memory.used_gb} / {$resources.memory.total_gb} GB</span>
	</div>

	<!-- Storage per root -->
	{#if $resources.storage.length}
		<div class="stats-bar-divider shrink-0"></div>
		<div class="stats-bar-group flex items-center gap-3 overflow-hidden">
			{#each $resources.storage as s (s.path)}
				<a href={filesHref(s.name)} class="stats-bar-link flex shrink-0 items-center gap-1.5">
					<span class="stats-bar-name">{s.name}</span>
					<div class="progress progress-sm stats-bar-track stats-bar-track-sm">
						<div class="progress-track">
							<div class="progress-fill" data-bar={barColor(s.percent, 'disk')} style:--progress="{Math.min(100, s.percent)}%"></div>
						</div>
					</div>
					<span class="stats-bar-slot stats-bar-slot-free shrink-0">{s.free_gb} GB</span>
				</a>
			{/each}
		</div>
	{/if}
</div>

<style>
	.stats-bar {
		position: fixed;
		bottom: 0;
		left: 0;
		right: 0;
		z-index: 30;
		font-variant-numeric: tabular-nums;
		border-top: 1px solid var(--color-border);
		background: var(--color-surface);
		padding: 0 1rem;
	}
	.stats-bar-group {
		font-size: 0.6875rem;
		color: var(--color-text-muted);
	}
	.stats-bar-divider {
		height: 1.25rem;
		width: 1px;
		background: var(--color-border);
	}
	.stats-bar-track {
		width: 4rem;
	}
	.stats-bar-track-sm {
		width: 3rem;
	}
	.stats-bar-slot {
		/* fixed-width slots so the digits don't reflow neighbouring bars as
		   they tick over. */
		display: inline-block;
	}
	.stats-bar-slot-pct {
		width: 2.25rem;
		text-align: right;
	}
	.stats-bar-slot-mem {
		width: 6rem;
	}
	.stats-bar-slot-free {
		width: 4.5rem;
	}
	.stats-bar-name {
		color: var(--color-text-faint);
	}
	.stats-bar-link {
		color: inherit;
		transition: color var(--motion-fast) var(--ease);
	}
	.stats-bar-link:hover {
		color: var(--color-primary-text);
	}
</style>
