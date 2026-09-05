<script lang="ts">
	import { dashboard } from '$lib/stores/dashboard';
	import { countRipping } from '$lib/utils/job-status';
	import SidebarStats from './SidebarStats.svelte';

	interface Props {
		/** Called when any link inside the panel is clicked (so the drawer can close). */
		onnavigate?: () => void;
	}

	let { onnavigate }: Props = $props();

	const rippingCount = $derived(countRipping($dashboard.active_jobs ?? []));

	// Links inside SidebarStats (storage rows) must also close the drawer, so
	// catch link clicks at the panel root instead of per-anchor. Keyboard
	// activation of a link fires a click event too, so no keydown handler is
	// needed here.
	function handleClick(e: MouseEvent) {
		if ((e.target as Element).closest('a')) onnavigate?.();
	}

	const services = $derived([
		{
			label: 'ARM',
			href: '/settings#system',
			ok: $dashboard.arm_online,
			dot: $dashboard.arm_online ? 'bg-green-500' : 'bg-red-500'
		},
		{
			label: 'DB',
			href: '/settings#system',
			ok: $dashboard.db_available,
			dot: $dashboard.db_available ? 'bg-green-500' : 'bg-yellow-500'
		},
		{
			label: 'Transcode',
			href: '/transcoder',
			ok: $dashboard.transcoder_online,
			dot:
				$dashboard.transcoder_online && ($dashboard.transcoder_stats?.worker_running ?? true)
					? 'bg-green-500'
					: $dashboard.transcoder_online
						? 'bg-yellow-500'
						: 'bg-gray-400'
		},
		{
			label: 'Key',
			href: '/settings#Metadata/makemkv_key',
			ok: $dashboard.makemkv_key_valid === true,
			dot: $dashboard.makemkv_key_valid === true ? 'bg-green-500' : 'bg-red-500'
		}
	]);
</script>

<!-- svelte-ignore a11y_click_events_have_key_events, a11y_no_static_element_interactions -->
<div data-mobile-stats class="flex-1 overflow-y-auto" onclick={handleClick}>
	<div class="px-3 py-4">
		<p class="mb-2 px-3 text-[10px] font-semibold uppercase tracking-wider text-gray-400 dark:text-gray-500">
			Services
		</p>
		<div class="space-y-1">
			{#each services as s (s.label)}
				<a
					href={s.href}
					class="flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium text-gray-700 transition-colors hover:bg-primary/10 dark:text-gray-300 dark:hover:bg-primary/15"
				>
					<div class="h-2.5 w-2.5 shrink-0 rounded-full {s.dot}"></div>
					{s.label}
				</a>
			{/each}
		</div>
	</div>

	<hr class="border-primary/20 dark:border-primary/20" />

	<div class="px-3 py-4">
		<p class="mb-2 px-3 text-[10px] font-semibold uppercase tracking-wider text-gray-400 dark:text-gray-500">
			Activity
		</p>
		<div class="space-y-1 text-sm">
			<a
				href="/settings#drives"
				class="block rounded-lg px-3 py-2 text-gray-700 transition-colors hover:bg-primary/10 dark:text-gray-300 dark:hover:bg-primary/15"
			>
				{$dashboard.db_available ? $dashboard.drives_online : '--'} drive{$dashboard.drives_online !== 1 ? 's' : ''}
			</a>
			{#if rippingCount > 0}
				<p class="px-3 py-2 font-semibold text-blue-600 dark:text-blue-400">{rippingCount} ripping</p>
			{/if}
			{#if $dashboard.active_transcodes.length > 0}
				<a
					href="/transcoder"
					class="block rounded-lg px-3 py-2 font-semibold text-indigo-600 transition-colors hover:bg-primary/10 dark:text-indigo-400 dark:hover:bg-primary/15"
				>
					{$dashboard.active_transcodes.length} transcoding
				</a>
			{/if}
			{#if $dashboard.transcoder_online && (Number($dashboard.transcoder_stats?.pending) || 0) > 0}
				<p class="px-3 py-2 font-semibold text-yellow-600 dark:text-yellow-400">
					{$dashboard.transcoder_stats?.pending} queued
				</p>
			{/if}
			{#if ($dashboard.notification_count ?? 0) > 0}
				<a
					href="/notifications"
					class="block rounded-lg px-3 py-2 font-semibold text-amber-600 transition-colors hover:bg-primary/10 dark:text-amber-400 dark:hover:bg-primary/15"
				>
					{$dashboard.notification_count} notification{$dashboard.notification_count !== 1 ? 's' : ''}
				</a>
			{/if}
		</div>
	</div>

	<SidebarStats />
</div>
