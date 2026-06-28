<script lang="ts">
	// SidebarStats reads from the resources store.
	// BottomStatsBar owns the lifecycle (startResources/stopResources);
	// SidebarStats is a pure reader — calling startResources() here is safe
	// because start() resets any prior timer (idempotent), but to keep things
	// simple we only read $resources. If SidebarStats renders without
	// BottomStatsBar mounted, resources will show the initial empty snapshot
	// until BottomStatsBar mounts and starts the poll.
	import { resources } from '$lib/stores/resources.svelte';

	function barColor(pct: number, kind: 'cpu' | 'mem' | 'disk'): string {
		if (pct >= 90) return 'bg-red-500';
		if (pct >= 70) return 'bg-yellow-500';
		return kind === 'cpu' ? 'bg-cyan-500' : kind === 'mem' ? 'bg-violet-500' : 'bg-emerald-500';
	}
</script>

<div data-sidebar-stats class="border-t border-primary/20 px-3 py-3 dark:border-primary/20">
	<div class="space-y-2">
		<!-- CPU -->
		<div>
			<div class="mb-0.5 flex items-center justify-between text-[11px] text-gray-500 dark:text-gray-400">
				<span>CPU</span>
				<span class="whitespace-nowrap">
					{$resources.cpu_percent.toFixed(0)}%
					{#if ($resources.cpu_temp ?? 0) > 0}
						<span class="text-orange-500">&nbsp;{($resources.cpu_temp ?? 0).toFixed(0)}&deg;C</span>
					{/if}
				</span>
			</div>
			<div class="h-1 w-full rounded-full bg-primary/15 dark:bg-primary/15">
				<div
					class="h-1 rounded-full transition-all duration-500 {barColor($resources.cpu_percent, 'cpu')}"
					style="width: {Math.min(100, $resources.cpu_percent)}%"
				></div>
			</div>
		</div>

		<!-- Memory -->
		<div>
			<div class="mb-0.5 flex items-center justify-between text-[11px] text-gray-500 dark:text-gray-400">
				<span>Mem</span>
				<span>{$resources.memory.used_gb} / {$resources.memory.total_gb} GB</span>
			</div>
			<div class="h-1 w-full rounded-full bg-primary/15 dark:bg-primary/15">
				<div
					class="h-1 rounded-full transition-all duration-500 {barColor($resources.memory.percent, 'mem')}"
					style="width: {Math.min(100, $resources.memory.percent)}%"
				></div>
			</div>
		</div>
	</div>

	<!-- Storage -->
	{#if $resources.storage.length}
		<div class="mt-3 space-y-2">
			<p class="text-[10px] font-semibold uppercase tracking-wider text-gray-400 dark:text-gray-500">Storage</p>
			{#each $resources.storage as s (s.path)}
				<a
					href="/files"
					class="block rounded-sm transition-colors hover:bg-primary/5 dark:hover:bg-primary/10 -mx-1 px-1"
				>
					<div class="mb-0.5 flex items-center justify-between text-[11px] text-gray-500 dark:text-gray-400">
						<span>{s.name}</span>
						<span>{s.free_gb} GB free</span>
					</div>
					<div class="h-1 w-full rounded-full bg-primary/15 dark:bg-primary/15">
						<div
							class="h-1 rounded-full transition-all duration-500 {barColor(s.percent, 'disk')}"
							style="width: {Math.min(100, s.percent)}%"
						></div>
					</div>
				</a>
			{/each}
		</div>
	{/if}
</div>
