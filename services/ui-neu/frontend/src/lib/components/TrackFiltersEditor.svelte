<script lang="ts">
	// Ported from services/ui/src/components/TrackFiltersEditor.vue.
	// Model is the `track_filters_json` shape; all conditions are ANDed.
	type TrackFilters = {
		min_duration_seconds?: number | null;
		max_duration_seconds?: number | null;
		title_indices?: number[] | null; // allowlist
		title_indices_exclude?: number[] | null; // blocklist
	};

	let { value, onchange }: { value: TrackFilters; onchange: (v: TrackFilters) => void } = $props();

	function update<K extends keyof TrackFilters>(key: K, val: TrackFilters[K]): void {
		onchange({ ...value, [key]: val });
	}

	// Parsing copied verbatim from the Vue source.
	function parseList(v: string): number[] {
		return v
			.split(/[ ,]+/)
			.map((s) => Number(s))
			.filter((n) => Number.isInteger(n) && n > 0);
	}

	function onList(key: 'title_indices' | 'title_indices_exclude', v: string): void {
		const parsed = parseList(v);
		update(key, parsed.length ? parsed : null);
	}

	function onDuration(key: 'min_duration_seconds' | 'max_duration_seconds', v: string): void {
		update(key, v ? Number(v) : null);
	}

	const allowList = $derived((value.title_indices ?? []).join(', '));
	const blockList = $derived((value.title_indices_exclude ?? []).join(', '));
</script>

<div class="panel-section track-filters-editor">
	<h4 class="track-filters-editor-title">Custom track filters</h4>
	<p class="track-filters-editor-hint">
		All conditions are ANDed. Indices come from the rip log's MakeMKV title list.
	</p>

	<label class="field track-filters-editor-field">
		<span class="field-label">Min duration (seconds)</span>
		<input
			id="tf-min-duration"
			data-testid="tf-min-duration"
			type="number"
			value={value.min_duration_seconds ?? ''}
			oninput={(e) => onDuration('min_duration_seconds', e.currentTarget.value)}
		/>
	</label>

	<label class="field track-filters-editor-field">
		<span class="field-label">Max duration (seconds)</span>
		<input
			id="tf-max-duration"
			data-testid="tf-max-duration"
			type="number"
			value={value.max_duration_seconds ?? ''}
			oninput={(e) => onDuration('max_duration_seconds', e.currentTarget.value)}
		/>
	</label>

	<label class="field track-filters-editor-field">
		<span class="field-label">Title indices (allowlist)</span>
		<input
			id="tf-allowlist"
			data-testid="tf-allowlist"
			type="text"
			placeholder="e.g. 1, 3, 5"
			value={allowList}
			oninput={(e) => onList('title_indices', e.currentTarget.value)}
		/>
	</label>

	<label class="field track-filters-editor-field">
		<span class="field-label">Title indices (blocklist)</span>
		<input
			id="tf-blocklist"
			data-testid="tf-blocklist"
			type="text"
			placeholder="e.g. 2, 4"
			value={blockList}
			oninput={(e) => onList('title_indices_exclude', e.currentTarget.value)}
		/>
	</label>
</div>

<style>
	/* original: mt-2 rounded-lg border border-gray-200 bg-gray-50/50 p-4 -
	   panel-section's own padding (1rem, matches) and background
	   (primary-tint-1) are close, but the outer mt-2 spacing to this
	   component's own caller (RipPresetForm's .stack) needs restating since
	   .stack's gap does not apply between a sibling and this component's own
	   root margin. */
	.track-filters-editor { margin-top: 0.5rem; }
	.track-filters-editor-title { font-size: 0.875rem; font-weight: 600; color: var(--color-text); }
	.track-filters-editor-hint { margin-top: 0.25rem; font-size: 0.75rem; color: var(--color-text-muted); }
	.track-filters-editor-field { margin-top: 0.75rem; }
</style>
