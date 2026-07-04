<script lang="ts">
	import { resources } from '$lib/stores/resources.svelte';
	import { resolveActiveHost, setActiveHost } from '$lib/stores/active-host.svelte';
	import { barColor, filesHref } from '$lib/utils/resource-bars';

	// Backend-first ordering, then rippers by hostname.
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

<div data-sidebar-stats class="border-t border-primary/20 px-3 py-3 dark:border-primary/20">
	{#if ordered.length > 1}
		<div class="mb-2 flex gap-1 overflow-x-auto">
			{#each ordered as v (v.hostname)}
				<button
					type="button"
					onclick={() => setActiveHost(v.hostname)}
					class="whitespace-nowrap border-b-2 px-1.5 py-0.5 text-[11px] font-medium transition-colors {active ===
					v.hostname
						? 'border-primary text-primary-text dark:border-primary-text-dark dark:text-primary-text-dark'
						: 'border-transparent text-gray-500 hover:text-gray-700 dark:text-gray-400 dark:hover:text-gray-300'}"
				>
					{tabLabel(v.role, v.hostname)}
				</button>
			{/each}
		</div>
	{/if}

	{#if current}
		{@const snap = current.snapshot}
		<div class="space-y-2">
			<!-- CPU -->
			<div>
				<div class="mb-0.5 flex items-center justify-between text-[11px] text-gray-500 dark:text-gray-400">
					<span>CPU</span>
					<span class="whitespace-nowrap">
						{snap.cpu_percent.toFixed(0)}%
						{#if (snap.cpu_temp ?? 0) > 0}
							<span class="text-orange-500">&nbsp;{(snap.cpu_temp ?? 0).toFixed(0)}&deg;C</span>
						{/if}
					</span>
				</div>
				<div class="h-1 w-full rounded-full bg-primary/15 dark:bg-primary/15">
					<div
						class="h-1 rounded-full transition-all duration-500 {barColor(snap.cpu_percent, 'cpu')}"
						style="width: {Math.min(100, snap.cpu_percent)}%"
					></div>
				</div>
			</div>

			<!-- Memory -->
			<div>
				<div class="mb-0.5 flex items-center justify-between text-[11px] text-gray-500 dark:text-gray-400">
					<span>Mem</span>
					<span>{snap.memory.used_gb} / {snap.memory.total_gb} GB</span>
				</div>
				<div class="h-1 w-full rounded-full bg-primary/15 dark:bg-primary/15">
					<div
						class="h-1 rounded-full transition-all duration-500 {barColor(snap.memory.percent, 'mem')}"
						style="width: {Math.min(100, snap.memory.percent)}%"
					></div>
				</div>
			</div>
		</div>

		<!-- Storage -->
		{#if snap.storage.length}
			<div class="mt-3 space-y-2">
				<p class="text-[10px] font-semibold uppercase tracking-wider text-gray-400 dark:text-gray-500">Storage</p>
				{#each snap.storage as s (s.path)}
					<a
						href={filesHref(s.name)}
						class="-mx-1 block rounded-sm px-1 transition-colors hover:bg-primary/5 dark:hover:bg-primary/10"
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
	{/if}
</div>
