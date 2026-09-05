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
<div class="fixed bottom-0 left-0 right-0 z-30 hidden h-10 items-center gap-3 border-t border-primary/20 bg-surface px-4 lg:flex 2xl:hidden dark:border-primary/20 dark:bg-surface-dark">
	<!-- CPU -->
	<div class="flex items-center gap-2 text-[11px] text-gray-500 dark:text-gray-400">
		<span class="shrink-0">CPU</span>
		<div class="h-1 w-16 rounded-full bg-primary/15 dark:bg-primary/15">
			<div class="h-1 rounded-full transition-all duration-500 {barColor($resources.cpu_percent, 'cpu')}" style="width: {Math.min(100, $resources.cpu_percent)}%"></div>
		</div>
		<span class="shrink-0">{$resources.cpu_percent.toFixed(0)}%</span>
	</div>

	<div class="h-5 w-px shrink-0 bg-primary/15 dark:bg-primary/20"></div>

	<!-- Memory -->
	<div class="flex items-center gap-2 text-[11px] text-gray-500 dark:text-gray-400">
		<span class="shrink-0">Mem</span>
		<div class="h-1 w-16 rounded-full bg-primary/15 dark:bg-primary/15">
			<div class="h-1 rounded-full transition-all duration-500 {barColor($resources.memory.percent, 'mem')}" style="width: {Math.min(100, $resources.memory.percent)}%"></div>
		</div>
		<span class="shrink-0 whitespace-nowrap">{$resources.memory.used_gb} / {$resources.memory.total_gb} GB</span>
	</div>

	<!-- Storage per root -->
	{#if $resources.storage.length}
		<div class="h-5 w-px shrink-0 bg-primary/15 dark:bg-primary/20"></div>
		<div class="flex items-center gap-3 overflow-hidden text-[11px] text-gray-500 dark:text-gray-400">
			{#each $resources.storage as s (s.path)}
				<a href={filesHref(s.name)} class="flex shrink-0 items-center gap-1.5 transition-colors hover:text-primary-text dark:hover:text-primary-text-dark">
					<span class="text-gray-400 dark:text-gray-500">{s.name}</span>
					<div class="h-1 w-12 rounded-full bg-primary/15 dark:bg-primary/15">
						<div class="h-1 rounded-full transition-all duration-500 {barColor(s.percent, 'disk')}" style="width: {Math.min(100, s.percent)}%"></div>
					</div>
					<span>{s.free_gb} GB</span>
				</a>
			{/each}
		</div>
	{/if}
</div>
