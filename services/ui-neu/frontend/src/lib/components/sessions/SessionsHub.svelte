<script lang="ts">
	import type { JoinedSession } from './sessionsData.svelte';
	import type { MediaType } from '$lib/types/api.gen';
	import SessionCard from './SessionCard.svelte';

	interface Props {
		sessions: JoinedSession[];
		typeCounts: Record<string, number>;
		loading: boolean;
		onedit: (session: JoinedSession) => void;
		onclone: (session: JoinedSession) => void;
		ondelete: (session: JoinedSession) => void;
		onnew: () => void;
	}

	let { sessions, typeCounts, loading, onedit, onclone, ondelete, onnew }: Props = $props();

	// Local filter state
	let search = $state('');
	let sourceFilter = $state<'all' | 'builtin' | 'custom'>('all');
	let transcodeFilter = $state<'any' | 'has' | 'none'>('any');
	let typeFilter = $state<MediaType | 'all'>('all');

	// Media type chips
	const MEDIA_TYPES: Array<{ key: MediaType | 'all'; label: string }> = [
		{ key: 'all', label: 'All' },
		{ key: 'movie', label: 'Movie' },
		{ key: 'tv', label: 'TV' },
		{ key: 'music', label: 'Music' },
		{ key: 'data', label: 'Data' },
		{ key: 'iso', label: 'ISO' },
	];

	// Derived visible list applying all filters
	const visible = $derived(
		sessions.filter((s) => {
			// Search filter
			if (search.trim() && !s.name.toLowerCase().includes(search.trim().toLowerCase())) {
				return false;
			}
			// Source filter
			if (sourceFilter === 'builtin' && !s.is_builtin) return false;
			if (sourceFilter === 'custom' && s.is_builtin) return false;
			// Transcode filter
			if (transcodeFilter === 'has' && s.transcode_preset_id == null) return false;
			if (transcodeFilter === 'none' && s.transcode_preset_id != null) return false;
			// Type filter
			if (typeFilter !== 'all' && s.media_type !== typeFilter) return false;
			return true;
		})
	);

	// Skeleton count for loading state
	const SKELETON_COUNT = 3;
</script>

<div class="flex flex-col gap-4">
	<!-- Search + filter container (hidden in the empty state — the guided panel
	     carries the only New-session button there, so it never appears twice) -->
	{#if sessions.length > 0}
	<div class="rounded-lg border border-primary/20 bg-surface px-4 py-3 shadow-xs dark:bg-surface-dark">
		<!-- Top row: search + inline REFINE dropdowns -->
		<div class="flex flex-wrap items-center gap-3">
			<input
				type="search"
				placeholder="Search sessions by name..."
				class="min-w-0 flex-1 rounded-md border border-gray-300 bg-white px-3 py-1.5 text-sm text-gray-900 shadow-xs placeholder:text-gray-400 focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary dark:border-gray-600 dark:bg-gray-800 dark:text-white dark:placeholder:text-gray-500"
				value={search}
				oninput={(e) => { search = (e.currentTarget as HTMLInputElement).value; }}
			/>

			<span class="shrink-0 text-xs font-semibold uppercase tracking-wide text-gray-400 dark:text-gray-500">Refine</span>

			<select
				aria-label="Filter by source"
				class="rounded-md border border-gray-300 bg-white px-2 py-1.5 text-sm text-gray-700 shadow-xs focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary dark:border-gray-600 dark:bg-gray-800 dark:text-gray-200"
				value={sourceFilter}
				onchange={(e) => { sourceFilter = (e.currentTarget as HTMLSelectElement).value as typeof sourceFilter; }}
			>
				<option value="all">All sources</option>
				<option value="builtin">Built-in only</option>
				<option value="custom">Custom only</option>
			</select>

			<select
				aria-label="Filter by transcode"
				class="rounded-md border border-gray-300 bg-white px-2 py-1.5 text-sm text-gray-700 shadow-xs focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary dark:border-gray-600 dark:bg-gray-800 dark:text-gray-200"
				value={transcodeFilter}
				onchange={(e) => { transcodeFilter = (e.currentTarget as HTMLSelectElement).value as typeof transcodeFilter; }}
			>
				<option value="any">Any transcode</option>
				<option value="has">Has transcode</option>
				<option value="none">Rip only</option>
			</select>
		</div>

		<hr class="my-3 border-primary/15" />

		<!-- Bottom row: TYPE chips + New session -->
		<div class="flex flex-wrap items-center gap-2">
			<span class="shrink-0 text-xs font-semibold uppercase tracking-wide text-gray-400 dark:text-gray-500">Type</span>
			{#each MEDIA_TYPES as chip}
				{@const count = typeCounts[chip.key] ?? 0}
				<button
					type="button"
					aria-pressed={typeFilter === chip.key}
					class="rounded-full border px-3 py-0.5 text-xs font-medium transition-colors
						{typeFilter === chip.key
							? 'border-primary bg-primary text-white'
							: 'border-gray-300 bg-white text-gray-600 hover:bg-gray-50 dark:border-gray-600 dark:bg-gray-800 dark:text-gray-300 dark:hover:bg-gray-700'}"
					onclick={() => { typeFilter = chip.key; }}
				>
					{chip.label} {count}
				</button>
			{/each}

			<!-- New session — pinned to the bottom-right of the filter panel -->
			<button
				type="button"
				onclick={onnew}
				class="ml-auto shrink-0 rounded-md bg-primary px-4 py-1.5 text-sm font-medium text-white hover:bg-primary/90 focus:outline-none focus:ring-2 focus:ring-primary focus:ring-offset-2"
			>
				+ New session
			</button>
		</div>
	</div>
	{/if}

	<!-- List area -->
	{#if loading}
		<!-- Loading skeletons -->
		<div class="flex flex-col gap-3">
			{#each Array(SKELETON_COUNT) as _}
				<div
					data-testid="session-skeleton"
					class="h-24 animate-pulse rounded-lg border border-primary/20 bg-gray-100 dark:bg-gray-800"
				></div>
			{/each}
		</div>
	{:else if sessions.length === 0}
		<!-- Guided empty panel -->
		<div class="flex flex-col items-center gap-4 rounded-lg border border-dashed border-gray-300 bg-gray-50 px-6 py-12 text-center dark:border-gray-600 dark:bg-gray-900/30">
			<p class="text-sm text-gray-500 dark:text-gray-400">
				No sessions yet. Sessions let you save your rip and transcode settings for quick reuse.
			</p>
			<button
				type="button"
				onclick={onnew}
				class="rounded-md bg-primary px-4 py-2 text-sm font-medium text-white hover:bg-primary/90 focus:outline-none focus:ring-2 focus:ring-primary focus:ring-offset-2"
			>
				New session
			</button>
		</div>
	{:else if visible.length === 0}
		<!-- No matches -->
		<p class="py-8 text-center text-sm text-gray-500 dark:text-gray-400">
			No sessions match your filters.
		</p>
	{:else}
		<!-- Session cards -->
		<div class="flex flex-col gap-3">
			{#each visible as session (session.id)}
				<SessionCard
					{session}
					onedit={() => onedit(session)}
					onclone={() => onclone(session)}
					ondelete={() => ondelete(session)}
				/>
			{/each}
		</div>
	{/if}
</div>
