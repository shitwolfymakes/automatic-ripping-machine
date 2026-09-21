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

	const inputClass =
		'mt-1 w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 dark:border-gray-600 dark:bg-gray-800 dark:text-white';
	const labelClass = 'text-sm font-medium text-gray-700 dark:text-gray-300';
</script>

<div class="mt-2 rounded-lg border border-gray-200 bg-gray-50/50 p-4 dark:border-gray-700 dark:bg-gray-800/30">
	<h4 class="text-sm font-semibold text-gray-900 dark:text-white">Custom track filters</h4>
	<p class="mt-1 text-xs text-gray-500 dark:text-gray-400">
		All conditions are ANDed. Indices come from the rip log's MakeMKV title list.
	</p>

	<div class="mt-3">
		<label class={labelClass} for="tf-min-duration">Min duration (seconds)</label>
		<input
			id="tf-min-duration"
			data-testid="tf-min-duration"
			type="number"
			class={inputClass}
			value={value.min_duration_seconds ?? ''}
			oninput={(e) => onDuration('min_duration_seconds', e.currentTarget.value)}
		/>
	</div>

	<div class="mt-3">
		<label class={labelClass} for="tf-max-duration">Max duration (seconds)</label>
		<input
			id="tf-max-duration"
			data-testid="tf-max-duration"
			type="number"
			class={inputClass}
			value={value.max_duration_seconds ?? ''}
			oninput={(e) => onDuration('max_duration_seconds', e.currentTarget.value)}
		/>
	</div>

	<div class="mt-3">
		<label class={labelClass} for="tf-allowlist">Title indices (allowlist)</label>
		<input
			id="tf-allowlist"
			data-testid="tf-allowlist"
			type="text"
			placeholder="e.g. 1, 3, 5"
			class={inputClass}
			value={allowList}
			oninput={(e) => onList('title_indices', e.currentTarget.value)}
		/>
	</div>

	<div class="mt-3">
		<label class={labelClass} for="tf-blocklist">Title indices (blocklist)</label>
		<input
			id="tf-blocklist"
			data-testid="tf-blocklist"
			type="text"
			placeholder="e.g. 2, 4"
			class={inputClass}
			value={blockList}
			oninput={(e) => onList('title_indices_exclude', e.currentTarget.value)}
		/>
	</div>
</div>
