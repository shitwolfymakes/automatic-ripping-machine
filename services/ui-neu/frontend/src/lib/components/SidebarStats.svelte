<script lang="ts">
	// SidebarStats reads from the resources store.
	// BottomStatsBar owns the lifecycle (startResources/stopResources);
	// SidebarStats is a pure reader — calling startResources() here is safe
	// because start() resets any prior timer (idempotent), but to keep things
	// simple we only read $resources. If SidebarStats renders without
	// BottomStatsBar mounted, resources will show the initial empty snapshot
	// until BottomStatsBar mounts and starts the poll.
	import { resources } from '$lib/stores/resources.svelte';
	import { barColor, filesHref } from '$lib/utils/resource-bars';
</script>

<div data-sidebar-stats class="stats-bar-side">
	<div class="stack stack-sm">
		<!-- CPU -->
		<div>
			<div class="stats-bar-side-label flex items-center justify-between">
				<span>CPU</span>
				<span class="whitespace-nowrap">
					{$resources.cpu_percent.toFixed(0)}%
					{#if ($resources.cpu_temp ?? 0) > 0}
						<span class="stats-bar-side-temp">&nbsp;{($resources.cpu_temp ?? 0).toFixed(0)}&deg;C</span>
					{/if}
				</span>
			</div>
			<div class="progress progress-sm">
				<div class="progress-track">
					<div class="progress-fill" data-bar={barColor($resources.cpu_percent, 'cpu')} style:--progress="{Math.min(100, $resources.cpu_percent)}%"></div>
				</div>
			</div>
		</div>

		<!-- Memory -->
		<div>
			<div class="stats-bar-side-label flex items-center justify-between">
				<span>Mem</span>
				<span>{$resources.memory.used_gb} / {$resources.memory.total_gb} GB</span>
			</div>
			<div class="progress progress-sm">
				<div class="progress-track">
					<div class="progress-fill" data-bar={barColor($resources.memory.percent, 'mem')} style:--progress="{Math.min(100, $resources.memory.percent)}%"></div>
				</div>
			</div>
		</div>
	</div>

	<!-- Storage -->
	{#if $resources.storage.length}
		<div class="stack stack-sm stats-bar-side-storage">
			<p class="eyebrow sidebar-stats-heading">Storage</p>
			{#each $resources.storage as s (s.path)}
				<a href={filesHref(s.name)} class="stats-bar-side-row">
					<div class="stats-bar-side-label flex items-center justify-between">
						<span>{s.name}</span>
						<span>{s.free_gb} GB free</span>
					</div>
					<div class="progress progress-sm">
						<div class="progress-track">
							<div class="progress-fill" data-bar={barColor(s.percent, 'disk')} style:--progress="{Math.min(100, s.percent)}%"></div>
						</div>
					</div>
				</a>
			{/each}
		</div>
	{/if}
</div>

<style>
	.stats-bar-side {
		font-variant-numeric: tabular-nums;
		border-top: 1px solid var(--color-border);
		padding: 0.75rem;
	}
	.stats-bar-side-label {
		margin-bottom: 0.125rem;
		font-size: 0.6875rem;
		color: var(--color-text-muted);
	}
	.stats-bar-side-temp {
		color: var(--color-accent-1);
	}
	.stats-bar-side-storage {
		margin-top: 0.75rem;
	}
	/* The eyebrow block is 11px/0.12em; this panel heading has always been
	   10px/0.05em, and the extra height shifts the storage rows below it. */
	.sidebar-stats-heading {
		font-size: 10px;
		line-height: 1.5;
		letter-spacing: 0.05em;
		color: var(--color-text-faint);
	}
	.stats-bar-side-row {
		display: block;
		margin: 0 -0.25rem;
		padding: 0 0.25rem;
		border-radius: var(--radius-sm);
		transition: background-color var(--motion-fast) var(--ease);
	}
	.stats-bar-side-row:hover {
		background: var(--color-primary-tint-1);
	}
</style>
