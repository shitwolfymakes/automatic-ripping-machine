<script lang="ts">
	import type { JoinedSession } from '../../stores/sessions-data.svelte';
	import type { MediaType } from '$lib/types/api.gen';
	import DataTable from '$lib/components/DataTable.svelte';
	import { encodersStore } from '$lib/stores/encoders.svelte';
	import { onMount } from 'svelte';
	import { resolveSample } from '../../sessions/sample-tokens';
	import { deleteGuard, openLabel, sessionColumns } from '../../sessions/table-columns';
	import MediaTypeChips from './MediaTypeChips.svelte';
	import {
		matchesFilters,
		matchesTranscode,
		type SourceFilter,
		type TranscodeFilter
	} from '../../sessions/list-filters';

	interface Props {
		sessions: JoinedSession[];
		typeCounts: Record<string, number>;
		loading: boolean;
		/** The id of the session whose editor is open, to highlight its row. */
		activeKey?: string | null;
		onedit: (session: JoinedSession) => void;
		onclone: (session: JoinedSession) => void;
		ondelete: (session: JoinedSession) => void;
		onnew: () => void;
	}

	let { sessions, typeCounts, loading, activeKey = null, onedit, onclone, ondelete, onnew }: Props = $props();

	// Local filter state
	let search = $state('');
	let sourceFilter = $state<SourceFilter>('all');
	let transcodeFilter = $state<TranscodeFilter>('any');
	let typeFilter = $state<MediaType | 'all'>('all');

	// Derived visible list applying all filters
	const visible = $derived(
		sessions.filter(
			(s) =>
				matchesFilters(s, { type: typeFilter, source: sourceFilter, search }) && matchesTranscode(s, transcodeFilter)
		)
	);

	// A session row carries its joined presets; the columns look them up by id.
	const columns = sessionColumns({
		rip: (id) => sessions.find((s) => s.rip_preset_id === id)?.ripPreset,
		transcode: (id) => sessions.find((s) => s.transcode_preset_id === id)?.transcodePreset,
		samplePath: (s) => resolveSample(s.output_path_template, s.media_type)
	});

	// The encoder label names encoders from the shared catalog.
	onMount(() => {
		encodersStore.load();
	});

	// Skeleton count for loading state
	const SKELETON_COUNT = 3;
</script>

{#snippet sessionActions(session: JoinedSession)}
	<div class="sessions-hub-actions">
		<button type="button" class="btn btn-sm" onclick={() => onedit(session)}>{openLabel(session)}</button>
		<button type="button" class="btn btn-sm" onclick={() => onclone(session)}>Clone</button>
		<button
			type="button"
			class="btn btn-danger btn-sm"
			disabled={deleteGuard(session, 0).disabled}
			title={session.is_builtin ? 'Built-in session: clone to customise' : undefined}
			onclick={() => ondelete(session)}>Delete</button
		>
	</div>
{/snippet}

<div class="stack">
	<!-- Search + filter container (hidden in the empty state — the guided panel
	     carries the only New-session button there, so it never appears twice) -->
	{#if sessions.length > 0}
		<div class="panel sessions-hub-bar">
			<!-- Top row: search + inline REFINE dropdowns -->
			<div class="cluster sessions-hub-filter-row">
				<input
					type="search"
					placeholder="Search sessions by name..."
					class="field-control sessions-hub-search"
					value={search}
					oninput={(e) => {
						search = (e.currentTarget as HTMLInputElement).value;
					}}
				/>

				<span class="sessions-hub-label">Refine</span>

				<select
					aria-label="Filter by source"
					class="field-control sessions-hub-select"
					value={sourceFilter}
					onchange={(e) => {
						sourceFilter = (e.currentTarget as HTMLSelectElement).value as typeof sourceFilter;
					}}
				>
					<option value="all">All sources</option>
					<option value="builtin">Built-in only</option>
					<option value="custom">Custom only</option>
				</select>

				<select
					aria-label="Filter by transcode"
					class="field-control sessions-hub-select"
					value={transcodeFilter}
					onchange={(e) => {
						transcodeFilter = (e.currentTarget as HTMLSelectElement).value as typeof transcodeFilter;
					}}
				>
					<option value="any">Any transcode</option>
					<option value="has">Has transcode</option>
					<option value="none">Rip only</option>
				</select>
			</div>

			<hr class="sessions-hub-divider" />

			<!-- Bottom row: TYPE chips + New session -->
			<div class="cluster sessions-hub-type-row">
				<span class="sessions-hub-label">Type</span>
				<MediaTypeChips counts={typeCounts} bind:selected={typeFilter} />

				<!-- New session — pinned to the bottom-right of the filter panel -->
				<button type="button" onclick={onnew} class="btn btn-primary sessions-hub-new-btn"> + New session </button>
			</div>
		</div>
	{/if}

	<!-- List area -->
	{#if loading}
		<!-- Loading skeletons -->
		<div class="stack stack-sm">
			{#each Array(SKELETON_COUNT) as _, i (i)}
				<div data-testid="session-skeleton" class="skeleton sessions-hub-skeleton"></div>
			{/each}
		</div>
	{:else if sessions.length === 0}
		<!-- Guided empty panel -->
		<div class="stack sessions-hub-empty">
			<p class="sessions-hub-empty-text">
				No sessions yet. Sessions let you save your rip and transcode settings for quick reuse.
			</p>
			<button type="button" onclick={onnew} class="btn btn-primary sessions-hub-empty-new-btn"> New session </button>
		</div>
	{:else if visible.length === 0}
		<!-- No matches -->
		<p class="sessions-hub-no-matches">No sessions match your filters.</p>
	{:else}
		<h3 class="sr-only">Sessions</h3>
		<DataTable {columns} rows={visible} rowKey={(s) => s.id} {activeKey} label="Sessions" actions={sessionActions} />
	{/if}
</div>

<style>
	.sessions-hub-actions {
		display: flex;
		justify-content: flex-end;
		gap: 0.375rem;
	}
	/* original bar: rounded-lg border border-primary/20 bg-surface px-4 py-3
	   shadow-xs dark:bg-surface-dark - .panel's own padding is 1rem all round,
	   not the original's 1rem/0.75rem; restated to match. */
	.sessions-hub-bar {
		padding: 0.75rem 1rem;
	}
	/* original top row: flex flex-wrap items-center gap-3 (0.75rem) -
	   .cluster's own shared gap (0.5rem) is tuned for the tighter TYPE chip
	   row below, so the wider filter-row gap is restated here. */
	.sessions-hub-filter-row {
		gap: 0.75rem;
	}
	/* original search input: px-3 py-1.5 (0.75rem/0.375rem) - field-control's
	   shared padding (0.5rem 0.75rem) is 2px taller per edge than the
	   compact filter-bar control the original was; vertical padding restated
	   to match (horizontal already agrees). */
	/* field-control's shared min-height (--control-h, 2.25rem) is a floor
	   tuned for full-size fields; this compact filter-bar control never had
	   one (original height was padding+line-height+border = 34px, under the
	   floor), so it's released back to content height. */
	/* field-control's shared fill/border are the primary-tinted look, tuned
	   for fields whose original was already a translucent primary tint (see
	   LogView's search input); this search input's original was genuinely
	   bg-white border-gray-300, a neutral surface, so both are restated back
	   to the nearest neutral-role tokens. --color-border-strong is also
	   primary-tinted (no neutral gray-300 token exists); --color-border is
	   the lighter of the two color-mix values and closer to the original,
	   with a small residual accepted as a genuine token collapse. */
	.sessions-hub-search {
		min-width: 0;
		flex: 1 1 0%;
		min-height: auto;
		padding-top: 0.375rem;
		padding-bottom: 0.375rem;
		background: var(--color-surface-raised);
		border-color: var(--color-border);
	}
	/* select's own text colour was text-gray-700 dark:text-gray-200, a shade
	   lighter than the search input's text-gray-900/white - field-control's
	   shared --color-text default is the search input's shade, so the two
	   selects need the secondary-text override to match their own original.
	   original selects: px-2 py-1.5 (0.5rem/0.375rem) - both edges restated
	   to match the compact filter-bar control (field-control's shared
	   padding is 0.75rem/0.5rem, sized for a full-size field). */
	/* same compact-control floor release as .sessions-hub-search above -
	   original select height (padding+line-height+border) was 32px, under
	   the shared 36px floor. */
	/* same neutral-surface override as .sessions-hub-search above - both
	   selects' originals were likewise bg-white border-gray-300. */
	.sessions-hub-select {
		width: auto;
		min-height: auto;
		color: var(--color-text-secondary);
		padding: 0.375rem 0.5rem;
		background: var(--color-surface-raised);
		border-color: var(--color-border);
	}
	/* original: text-xs font-semibold uppercase tracking-wide text-gray-400
	   dark:text-gray-500 (12px/16px, tracking 0.025em) - NOT .eyebrow's
	   metrics (10.5px, tracking 0.12em; that block is reserved for the
	   arbitrary text-[10.5px] tracking-[0.12em] string per the migration
	   reference), so restated in full (see OutputPathField.svelte's
	   identical label). */
	.sessions-hub-label {
		flex-shrink: 0;
		font-size: 0.75rem;
		line-height: 1rem;
		font-weight: 600;
		letter-spacing: 0.025em;
		text-transform: uppercase;
		color: var(--color-text-faint);
	}
	/* the divider's border-primary/15 maps to --color-border; hr's own
	   default border-top plus browser margin is overridden to the original's
	   my-3 (0.75rem) spacing, height 1px. */
	.sessions-hub-divider {
		margin: 0.75rem 0;
		border: 0;
		border-top: 1px solid var(--color-border);
	}
	/* original: rounded-md bg-primary ... px-4 py-1.5 text-sm hover:bg-primary/90
	   - no border/ring class at all; .btn-primary's own border is invisible
	   (same colour as the fill) but still occupies 2px of layout height, and
	   its default radius (--radius-lg) is bigger than the original's
	   --radius-md (Task 9/10 finding on bare fill buttons with no border
	   class). */
	/* original had no min-height at all (content height 32px, under .btn's
	   shared 36px floor) - the floor also stretched the whole TYPE chip row
	   via flex row-height, so it's released here to bring the row back to
	   32px alongside the chips (which never had the floor applied). */
	.sessions-hub-new-btn {
		margin-left: auto;
		flex-shrink: 0;
		min-height: auto;
		border: 0;
		border-radius: var(--radius-md);
		padding: 0.375rem 1rem;
	}
	/* original: rounded-md bg-primary px-4 py-2 text-sm ... - same no-border
	   pattern as .sessions-hub-new-btn above, but at .btn's own default
	   padding (0.5rem 1rem), so only border/radius need restating. */
	.sessions-hub-empty-new-btn {
		border: 0;
		border-radius: var(--radius-md);
	}
	/* original: h-24 animate-pulse rounded-lg border border-primary/20
	   bg-gray-100 dark:bg-gray-800 - taller and bordered compared to
	   .skeleton's shared background/animation, so radius/height/border are
	   restated (same pattern as PresetLibrary.svelte's skeleton). */
	.sessions-hub-skeleton {
		height: 6rem;
		border-radius: var(--radius-lg);
		border: 1px solid var(--color-border);
	}
	/* original empty panel: flex flex-col items-center gap-4 rounded-lg
	   border border-dashed border-gray-300 bg-gray-50 px-6 py-12 text-center
	   dark:border-gray-600 dark:bg-gray-900/30 - a dashed neutral panel with
	   no equivalent block. */
	.sessions-hub-empty {
		align-items: center;
		border: 1px dashed var(--color-border-strong);
		border-radius: var(--radius-lg);
		background: var(--color-primary-tint-1);
		padding: 3rem 1.5rem;
		text-align: center;
		gap: 1rem;
	}
	.sessions-hub-empty-text {
		font-size: 0.875rem;
		line-height: 1.25rem;
		color: var(--color-text-muted);
	}
	.sessions-hub-no-matches {
		padding: 2rem 0;
		text-align: center;
		font-size: 0.875rem;
		line-height: 1.25rem;
		color: var(--color-text-muted);
	}
</style>
