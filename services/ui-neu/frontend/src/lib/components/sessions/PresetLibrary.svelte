<script lang="ts">
	import type { RipPresetView, TranscodePresetView, MediaType } from '$lib/types/api.gen';
	import DataTable from '$lib/components/DataTable.svelte';
	import { deleteGuard, openLabel, ripPresetColumns, transcodePresetColumns } from './tableColumns';
	import { encodersStore } from '$lib/stores/encoders.svelte';
	import { onMount } from 'svelte';
	import MediaTypeChips from './MediaTypeChips.svelte';
	import { matchesFilters, type SourceFilter } from './listFilters';
	import { countByMediaType } from '$lib/utils/sessions';

	interface Props {
		/** Which preset kind this tab shows. */
		kind: 'rip' | 'transcode';
		ripPresets: RipPresetView[];
		transcodePresets: TranscodePresetView[];
		ripUsage: (id: string) => number;
		transcodeUsage: (id: string) => number;
		loading: boolean;
		/** The id of the preset whose editor is open, to highlight its row. */
		activeKey?: string | null;
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
		activeKey = null,
		onnewrip,
		onnewtranscode,
		onview,
		onedit,
		onclone,
		ondelete
	}: Props = $props();

	// ── Media-type filter ─────────────────────────────────────────────────────

	let typeFilter = $state<MediaType | 'all'>('all');
	let search = $state('');
	let sourceFilter = $state<SourceFilter>('all');

	function matches(p: RipPresetView | TranscodePresetView): boolean {
		return matchesFilters(p, { type: typeFilter, source: sourceFilter, search });
	}

	/** The preset's usage count, from the active kind's usage function. */
	function usage(id: string): number {
		return kind === 'rip' ? ripUsage(id) : transcodeUsage(id);
	}

	// The active kind's presets
	const presets = $derived(kind === 'rip' ? ripPresets : transcodePresets);

	// Derive preset counts per media type for the active kind only
	const presetTypeCounts = $derived(countByMediaType(presets));

	// Filtered preset list
	const visible = $derived(presets.filter(matches));
	const noun = $derived(kind === 'rip' ? 'rip presets' : 'transcode presets');
	const emptyText = $derived(`No ${noun} match the current filters.`);
	const heading = $derived(kind === 'rip' ? 'Rip presets' : 'Transcode presets');

	// Usage by preset id, for the Used by column and the Delete guard.
	const usageById = $derived(Object.fromEntries(presets.map((p) => [p.id, usage(p.id)])));
	const ripColumns = $derived(ripPresetColumns(usageById));
	const transcodeColumns = $derived(transcodePresetColumns(usageById));

	// The encoder column names encoders from the shared catalog.
	onMount(() => {
		encodersStore.load();
	});

	const SKELETON_COUNT = 3;
</script>

{#snippet presetActions(preset: RipPresetView | TranscodePresetView)}
	{@const guard = deleteGuard(preset, usageById[preset.id])}
	<div class="preset-library-actions">
		<button type="button" class="btn btn-sm" onclick={() => (preset.is_builtin ? onview(preset) : onedit(preset))}
			>{openLabel(preset)}</button
		>
		<button type="button" class="btn btn-sm" onclick={() => onclone(preset)}>Clone</button>
		<button
			type="button"
			class="btn btn-danger btn-sm"
			disabled={guard.disabled}
			title={guard.title}
			onclick={() => ondelete(preset)}>Delete</button
		>
	</div>
{/snippet}

<div class="stack stack-lg">
	<!-- Search + filter container: same structure as the Sessions root -->
	<div class="panel panel-compact preset-library-bar" data-testid="preset-action-bar">
		<!-- Top row: search + inline REFINE dropdown -->
		<div class="cluster preset-library-filters">
			<input
				type="search"
				placeholder="Search {noun} by name..."
				aria-label="Search {noun}"
				class="field-control preset-library-search"
				value={search}
				oninput={(e) => {
					search = (e.currentTarget as HTMLInputElement).value;
				}}
			/>

			<span class="eyebrow">Refine</span>

			<select
				aria-label="Filter by source"
				class="field-control preset-library-source"
				value={sourceFilter}
				onchange={(e) => {
					sourceFilter = (e.currentTarget as HTMLSelectElement).value as typeof sourceFilter;
				}}
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
			<MediaTypeChips counts={presetTypeCounts} bind:selected={typeFilter} />

			<button
				type="button"
				onclick={kind === 'rip' ? onnewrip : onnewtranscode}
				class="btn btn-primary preset-library-new-btn">+ New {kind} preset</button
			>
		</div>
	</div>

	{#if loading}
		<!-- Loading skeletons -->
		<div class="stack stack-sm">
			{#each Array(SKELETON_COUNT) as _, i (i)}
				<div data-testid="preset-skeleton" class="skeleton preset-library-skeleton"></div>
			{/each}
		</div>
	{:else}
		<!-- ── Preset list ─────────────────────────────────────────────────── -->
		<section>
			<h3 class="sr-only">{heading}</h3>

			{#if kind === 'rip'}
				<DataTable
					columns={ripColumns}
					rows={visible as RipPresetView[]}
					rowKey={(p) => p.id}
					{activeKey}
					label={heading}
					empty={emptyText}
					actions={presetActions}
				/>
			{:else}
				<DataTable
					columns={transcodeColumns}
					rows={visible as TranscodePresetView[]}
					rowKey={(p) => p.id}
					{activeKey}
					label={heading}
					empty={emptyText}
					actions={presetActions}
				/>
			{/if}
		</section>
	{/if}
</div>

<style>
	/* the original bar was px-4 py-3 (1rem/0.75rem); .panel-compact is
	   0.75rem all round, close but not identical on the horizontal axis. */
	.preset-library-bar {
		padding: 0.75rem 1rem;
	}
	/* search, REFINE and the select share one row, as on the Sessions view */
	.preset-library-filters {
		flex-wrap: nowrap;
	}
	.preset-library-search {
		min-width: 0;
		flex: 1 1 0%;
	}
	.preset-library-source {
		flex: none;
		width: auto;
	}
	/* the divider's own border-primary/15 maps to --color-border; hr's
	   default border-top plus browser margin is overridden to the original's
	   my-3 (0.75rem) spacing, height 1px. */
	.preset-library-divider {
		margin: 0.75rem 0;
		border: 0;
		border-top: 1px solid var(--color-border);
	}
	.preset-library-new-btn {
		margin-left: auto;
		flex-shrink: 0;
	}
	.preset-library-actions {
		display: flex;
		justify-content: flex-end;
		gap: 0.375rem;
	}
	/* original: h-16 rounded-lg border border-primary/20 bg-gray-100 - taller,
	   more-rounded, and bordered compared to .skeleton-block's 2.5rem/radius-sm/
	   no border. */
	.preset-library-skeleton {
		height: 4rem;
		border-radius: var(--radius-lg);
		border: 1px solid var(--color-border);
	}
</style>
