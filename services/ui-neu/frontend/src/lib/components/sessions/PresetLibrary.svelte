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
	const visibleRip = $derived(
		typeFilter === 'all'
			? ripPresets
			: ripPresets.filter((p) => p.media_type === typeFilter)
	);

	const visibleTranscode = $derived(
		typeFilter === 'all'
			? transcodePresets
			: transcodePresets.filter((p) => p.media_type === typeFilter)
	);

	const SKELETON_COUNT = 3;
</script>

<div class="flex flex-col gap-6">
	<!-- Filter bar: same top-bar card styling as the Sessions hub, with the
	     New-preset action pinned right like the hub's New session button -->
	<div class="rounded-lg border border-primary/20 bg-surface px-4 py-3 shadow-xs dark:bg-surface-dark">
		<div class="flex flex-wrap items-center gap-3">
			<span class="shrink-0 text-xs font-semibold uppercase tracking-wide text-gray-400 dark:text-gray-500">Refine</span>
			<!-- Media-type chip row (counts presets, not sessions) -->
			<div class="flex flex-wrap gap-2">
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
			</div>
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
			{#if visibleRip.length === 0}
				<p class="py-4 text-center text-sm text-gray-400 dark:text-gray-500">
					No rip presets match the selected filter.
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
			{#if visibleTranscode.length === 0}
				<p class="py-4 text-center text-sm text-gray-400 dark:text-gray-500">
					No transcode presets match the selected filter.
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
