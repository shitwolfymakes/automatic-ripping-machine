<script lang="ts">
	import type { RipPresetView, TranscodePresetView, MediaType } from '$lib/types/api.gen';
	import PresetRow from './PresetRow.svelte';

	interface Props {
		/** Which preset kind this tab shows. */
		kind: 'rip' | 'transcode';
		ripPresets: RipPresetView[];
		transcodePresets: TranscodePresetView[];
		ripUsage: (id: string) => number;
		transcodeUsage: (id: string) => number;
		loading: boolean;
		onnewrip: () => void;
		onnewtranscode: () => void;
		onview: (preset: RipPresetView | TranscodePresetView) => void;
		onedit: (preset: RipPresetView | TranscodePresetView) => void;
		onclone: (preset: RipPresetView | TranscodePresetView) => void;
		ondelete: (preset: RipPresetView | TranscodePresetView) => void;
	}

	let {
		kind,
		ripPresets,
		transcodePresets,
		ripUsage,
		transcodeUsage,
		loading,
		onnewrip,
		onnewtranscode,
		onview,
		onedit,
		onclone,
		ondelete,
	}: Props = $props();

	// ── Media-type filter ─────────────────────────────────────────────────────

	let typeFilter = $state<MediaType | 'all'>('all');
	let search = $state('');
	let sourceFilter = $state<'all' | 'builtin' | 'custom'>('all');

	function matches(p: RipPresetView | TranscodePresetView): boolean {
		if (typeFilter !== 'all' && p.media_type !== typeFilter) return false;
		if (sourceFilter === 'builtin' && !p.is_builtin) return false;
		if (sourceFilter === 'custom' && p.is_builtin) return false;
		const q = search.trim().toLowerCase();
		if (q && !p.name.toLowerCase().includes(q)) return false;
		return true;
	}

	const MEDIA_TYPES: Array<{ key: MediaType | 'all'; label: string }> = [
		{ key: 'all', label: 'All' },
		{ key: 'movie', label: 'Movie' },
		{ key: 'tv', label: 'TV' },
		{ key: 'music', label: 'Music' },
		{ key: 'data', label: 'Data' },
		{ key: 'iso', label: 'ISO' },
	];

	// Derive preset counts per media type for the active kind only
	const presetTypeCounts = $derived(
		(() => {
			const counts: Record<string, number> = { all: 0 };
			const source = kind === 'rip' ? ripPresets : transcodePresets;
			for (const p of source) {
				counts[p.media_type] = (counts[p.media_type] ?? 0) + 1;
				counts.all = (counts.all ?? 0) + 1;
			}
			return counts;
		})()
	);

	// Filtered preset lists
	const visibleRip = $derived(ripPresets.filter(matches));
	const visibleTranscode = $derived(transcodePresets.filter(matches));
	const noun = $derived(kind === 'rip' ? 'rip presets' : 'transcode presets');

	const SKELETON_COUNT = 3;
</script>

<div class="flex flex-col gap-6">
	<!-- Reusable note -->
	<p class="text-sm text-gray-500 dark:text-gray-400">
		Presets are reusable building blocks: each preset can be used by multiple sessions, and changing
		one affects every session that references it.
	</p>

	<!-- Search + filter container: same structure as the Sessions root -->
	<div class="rounded-lg border border-primary/20 bg-surface px-4 py-3 shadow-xs dark:bg-surface-dark" data-testid="preset-action-bar">
		<!-- Top row: search + inline REFINE dropdown -->
		<div class="flex flex-wrap items-center gap-3">
			<input
				type="search"
				placeholder="Search {noun} by name..."
				aria-label="Search {noun}"
				class="min-w-0 flex-1 rounded-md border border-gray-300 bg-white px-3 py-1.5 text-sm text-gray-900 shadow-xs placeholder:text-gray-400 focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary dark:border-gray-600 dark:bg-gray-800 dark:text-white"
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
		</div>

		<hr class="my-3 border-primary/15" />

		<!-- Bottom row: TYPE chips + New preset -->
		<div class="flex flex-wrap items-center gap-2">
			<span class="shrink-0 text-xs font-semibold uppercase tracking-wide text-gray-400 dark:text-gray-500">Type</span>
			{#each MEDIA_TYPES as chip}
				{@const count = presetTypeCounts[chip.key] ?? 0}
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

			{#if kind === 'rip'}
				<button
					type="button"
					onclick={onnewrip}
					class="ml-auto shrink-0 rounded-md bg-primary px-4 py-1.5 text-sm font-medium text-white hover:bg-primary/90 focus:outline-none focus:ring-2 focus:ring-primary focus:ring-offset-2"
				>+ New rip preset</button>
			{:else}
				<button
					type="button"
					onclick={onnewtranscode}
					class="ml-auto shrink-0 rounded-md bg-primary px-4 py-1.5 text-sm font-medium text-white hover:bg-primary/90 focus:outline-none focus:ring-2 focus:ring-primary focus:ring-offset-2"
				>+ New transcode preset</button>
			{/if}
		</div>
	</div>

	{#if loading}
		<!-- Loading skeletons -->
		<div class="flex flex-col gap-3">
			{#each Array(SKELETON_COUNT) as _}
				<div
					data-testid="preset-skeleton"
					class="h-16 animate-pulse rounded-lg border border-primary/20 bg-gray-100 dark:bg-gray-800"
				></div>
			{/each}
		</div>
	{:else if kind === 'rip'}
		<!-- ── Rip presets section ─────────────────────────────────────────── -->
		<section>
			<h3 class="sr-only">Rip presets</h3>

			{#if visibleRip.length === 0}
				<p class="py-4 text-center text-sm text-gray-400 dark:text-gray-500">
					No rip presets match the current filters.
				</p>
			{:else}
				<div class="flex flex-col gap-3">
					{#each visibleRip as preset (preset.id)}
						<PresetRow
							kind="rip"
							{preset}
							usedBy={ripUsage(preset.id)}
							onview={() => onview(preset)}
							onedit={() => onedit(preset)}
							onclone={() => onclone(preset)}
							ondelete={() => ondelete(preset)}
						/>
					{/each}
				</div>
			{/if}
		</section>
	{:else}
		<!-- ── Transcode presets section ──────────────────────────────────── -->
		<section>
			<h3 class="sr-only">Transcode presets</h3>

			{#if visibleTranscode.length === 0}
				<p class="py-4 text-center text-sm text-gray-400 dark:text-gray-500">
					No transcode presets match the current filters.
				</p>
			{:else}
				<div class="flex flex-col gap-3">
					{#each visibleTranscode as preset (preset.id)}
						<PresetRow
							kind="transcode"
							{preset}
							usedBy={transcodeUsage(preset.id)}
							onview={() => onview(preset)}
							onedit={() => onedit(preset)}
							onclone={() => onclone(preset)}
							ondelete={() => ondelete(preset)}
						/>
					{/each}
				</div>
			{/if}
		</section>
	{/if}
</div>
