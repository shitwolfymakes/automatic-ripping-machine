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

<div class="stack stack-lg">
	<!-- Reusable note -->
	<p class="preset-library-note">
		Presets are reusable building blocks: each preset can be used by multiple sessions, and changing
		one affects every session that references it.
	</p>

	<!-- Search + filter container: same structure as the Sessions root -->
	<div class="panel panel-compact preset-library-bar" data-testid="preset-action-bar">
		<!-- Top row: search + inline REFINE dropdown -->
		<div class="cluster">
			<input
				type="search"
				placeholder="Search {noun} by name..."
				aria-label="Search {noun}"
				class="field-control preset-library-search"
				value={search}
				oninput={(e) => { search = (e.currentTarget as HTMLInputElement).value; }}
			/>

			<span class="eyebrow">Refine</span>

			<select
				aria-label="Filter by source"
				class="field-control preset-library-source"
				value={sourceFilter}
				onchange={(e) => { sourceFilter = (e.currentTarget as HTMLSelectElement).value as typeof sourceFilter; }}
			>
				<option value="all">All sources</option>
				<option value="builtin">Built-in only</option>
				<option value="custom">Custom only</option>
			</select>
		</div>

		<hr class="preset-library-divider" />

		<!-- Bottom row: TYPE chips + New preset -->
		<div class="cluster">
			<span class="eyebrow">Type</span>
			{#each MEDIA_TYPES as chip}
				{@const count = presetTypeCounts[chip.key] ?? 0}
				<button
					type="button"
					aria-pressed={typeFilter === chip.key}
					class="chip preset-library-type-chip"
					onclick={() => { typeFilter = chip.key; }}
				>
					{chip.label} {count}
				</button>
			{/each}

			{#if kind === 'rip'}
				<button
					type="button"
					onclick={onnewrip}
					class="btn btn-primary preset-library-new-btn"
				>+ New rip preset</button>
			{:else}
				<button
					type="button"
					onclick={onnewtranscode}
					class="btn btn-primary preset-library-new-btn"
				>+ New transcode preset</button>
			{/if}
		</div>
	</div>

	{#if loading}
		<!-- Loading skeletons -->
		<div class="stack stack-sm">
			{#each Array(SKELETON_COUNT) as _}
				<div data-testid="preset-skeleton" class="skeleton preset-library-skeleton"></div>
			{/each}
		</div>
	{:else if kind === 'rip'}
		<!-- ── Rip presets section ─────────────────────────────────────────── -->
		<section>
			<h3 class="sr-only">Rip presets</h3>

			{#if visibleRip.length === 0}
				<p class="preset-library-empty">
					No rip presets match the current filters.
				</p>
			{:else}
				<div class="stack stack-sm">
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
				<p class="preset-library-empty">
					No transcode presets match the current filters.
				</p>
			{:else}
				<div class="stack stack-sm">
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

<style>
	.preset-library-note { font-size: 0.875rem; line-height: 1.25rem; color: var(--color-text-muted); }
	/* the original bar was px-4 py-3 (1rem/0.75rem); .panel-compact is
	   0.75rem all round, close but not identical on the horizontal axis. */
	.preset-library-bar { padding: 0.75rem 1rem; }
	.preset-library-search { min-width: 0; flex: 1 1 0%; }
	/* the divider's own border-primary/15 maps to --color-border; hr's
	   default border-top plus browser margin is overridden to the original's
	   my-3 (0.75rem) spacing, height 1px. */
	.preset-library-divider { margin: 0.75rem 0; border: 0; border-top: 1px solid var(--color-border); }
	/* chip's default modifiers are all solid-tone; the TYPE filter pills are
	   a plain bordered toggle (border-gray-300 bg-white, selected =
	   border-primary bg-primary), not chip's tinted-background look, so the
	   shape is redrawn here on top of chip's base sizing/cursor/transition. */
	.preset-library-type-chip { border: 1px solid var(--color-border-strong); border-radius: 9999px; background: var(--color-surface-raised); padding: 0.125rem 0.75rem; font-size: 0.75rem; font-weight: 500; color: var(--color-text-secondary); }
	.preset-library-type-chip:hover { background: var(--color-primary-tint-1); }
	.preset-library-type-chip[aria-pressed="true"] { border-color: var(--color-primary); background: var(--color-primary); color: var(--color-on-primary); }
	.preset-library-new-btn { margin-left: auto; flex-shrink: 0; }
	.preset-library-empty { padding: 1rem 0; text-align: center; font-size: 0.875rem; color: var(--color-text-faint); }
	/* original: h-16 rounded-lg border border-primary/20 bg-gray-100 - taller,
	   more-rounded, and bordered compared to .skeleton-block's 2.5rem/radius-sm/
	   no border. */
	.preset-library-skeleton { height: 4rem; border-radius: var(--radius-lg); border: 1px solid var(--color-border); }
</style>
