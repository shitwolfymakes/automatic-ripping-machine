<script lang="ts">
	import { onMount } from 'svelte';
	import { resources, startResources, stopResources } from '$lib/stores/resources.svelte';
	import { resolveActiveHost, setActiveHost } from '$lib/stores/active-host.svelte';
	import { barColor, filesHref } from '$lib/utils/resource-bars';
	import { reveal } from '$lib/transitions';

	onMount(() => {
		startResources();
		return () => stopResources();
	});

	const ordered = $derived(
		[...$resources].sort((a, b) => {
			if (a.role !== b.role) return a.role === 'backend' ? -1 : 1;
			return a.hostname.localeCompare(b.hostname);
		})
	);
	const hostnames = $derived(ordered.map((v) => v.hostname));

	// resolveActiveHost may reset the module-level selection as a side effect
	// (when the prior selection has gone stale), which Svelte 5 forbids inside
	// a $derived. Resolve it in an $effect and mirror the result into local
	// state instead.
	let active = $state<string | null>(null);
	$effect(() => {
		active = resolveActiveHost(hostnames);
	});
	const current = $derived(ordered.find((v) => v.hostname === active) ?? null);

	function tabLabel(role: string, hostname: string): string {
		return role === 'backend' ? 'Backend' : hostname;
	}
</script>

<!-- Fixed bottom bar, hidden below lg (1024px) — matches neu placement. -->
<div
	class="fixed bottom-0 left-0 right-0 z-30 hidden h-10 items-center gap-3 border-t border-primary/20 bg-surface px-4 lg:flex 2xl:hidden dark:border-primary/20 dark:bg-surface-dark"
>
	{#if ordered.length > 1}
		<div in:reveal class="flex shrink-0 gap-1">
			{#each ordered as v (v.hostname)}
				<button
					type="button"
					onclick={() => setActiveHost(v.hostname)}
					class="whitespace-nowrap border-b-2 px-1 text-[11px] font-medium transition-colors {active ===
					v.hostname
						? 'border-primary text-primary-text dark:border-primary-text-dark dark:text-primary-text-dark'
						: 'border-transparent text-gray-500 hover:text-gray-700 dark:text-gray-400 dark:hover:text-gray-300'}"
				>
					{tabLabel(v.role, v.hostname)}
				</button>
			{/each}
		</div>
		<div class="h-5 w-px shrink-0 bg-primary/15 dark:bg-primary/20"></div>
	{/if}

	{#if current}
		{@const snap = current.snapshot}
		<!-- CPU -->
		<div in:reveal class="flex items-center gap-2 text-[11px] text-gray-500 dark:text-gray-400">
			<span class="shrink-0">CPU</span>
			<div class="h-1 w-16 rounded-full bg-primary/15 dark:bg-primary/15">
				<div
					class="h-1 rounded-full transition-all duration-500 {barColor(snap.cpu_percent, 'cpu')}"
					style="width: {Math.min(100, snap.cpu_percent)}%"
				></div>
			</div>
			<span class="shrink-0">{snap.cpu_percent.toFixed(0)}%</span>
		</div>

		<div class="h-5 w-px shrink-0 bg-primary/15 dark:bg-primary/20"></div>

		<!-- Memory -->
		<div in:reveal class="flex items-center gap-2 text-[11px] text-gray-500 dark:text-gray-400">
			<span class="shrink-0">Mem</span>
			<div class="h-1 w-16 rounded-full bg-primary/15 dark:bg-primary/15">
				<div
					class="h-1 rounded-full transition-all duration-500 {barColor(snap.memory.percent, 'mem')}"
					style="width: {Math.min(100, snap.memory.percent)}%"
				></div>
			</div>
			<span class="shrink-0 whitespace-nowrap">{snap.memory.used_gb} / {snap.memory.total_gb} GB</span>
		</div>

		<!-- Storage per root -->
		{#if snap.storage.length}
			<div class="h-5 w-px shrink-0 bg-primary/15 dark:bg-primary/20"></div>
			<div in:reveal class="flex items-center gap-3 overflow-hidden text-[11px] text-gray-500 dark:text-gray-400">
				{#each snap.storage as s (s.path)}
					<a
						href={filesHref(s.name)}
						class="flex shrink-0 items-center gap-1.5 transition-colors hover:text-primary-text dark:hover:text-primary-text-dark"
					>
						<span class="text-gray-400 dark:text-gray-500">{s.name}</span>
						<div class="h-1 w-12 rounded-full bg-primary/15 dark:bg-primary/15">
							<div
								class="h-1 rounded-full transition-all duration-500 {barColor(s.percent, 'disk')}"
								style="width: {Math.min(100, s.percent)}%"
							></div>
						</div>
						<span>{s.free_gb} GB</span>
					</a>
				{/each}
			</div>
		{/if}
	{/if}
</div>
