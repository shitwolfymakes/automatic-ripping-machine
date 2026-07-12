<script lang="ts">
	// Ported from services/ui/src/views/RipPresetForm.vue. The Vue view is a
	// routed page; this is an inline (no-route) form driven by props. Field
	// wiring, the disabled rules, and the create / custom-edit / built-in
	// submit-body shapes follow the Vue source faithfully.
	import { createRipPreset, updateRipPreset } from '$lib/api/ripPresets';
	import TrackFiltersEditor from './TrackFiltersEditor.svelte';
	import type {
		IdentificationMode,
		MediaType,
		OutputMode,
		RipPresetView,
		TrackSelection
	} from '$lib/types/api.gen';

	type TrackFilters = {
		min_duration_seconds?: number | null;
		max_duration_seconds?: number | null;
		title_indices?: number[] | null;
		title_indices_exclude?: number[] | null;
	};

	let {
		preset = null,
		onsaved,
		oncancel
	}: {
		preset?: RipPresetView | null;
		onsaved: (p: RipPresetView) => void;
		oncancel: () => void;
	} = $props();

	const editing = $derived(!!preset);
	const isBuiltin = $derived(preset?.is_builtin ?? false);

	// Seed from the preset on edit, or the create-defaults otherwise.
	let name = $state(preset?.name ?? '');
	let mediaType = $state<MediaType>(preset?.media_type ?? 'movie');
	let trackSelection = $state<TrackSelection>(preset?.track_selection ?? 'main_feature');
	let identificationMode = $state<IdentificationMode>(
		preset?.identification_mode ?? 'required'
	);
	let outputMode = $state<OutputMode>(preset?.output_mode ?? 'tracks');
	let filters = $state<TrackFilters>((preset?.track_filters_json as TrackFilters) ?? {});

	let submitting = $state(false);
	let error = $state<string | null>(null);

	const showFilters = $derived(trackSelection === 'custom' && !isBuiltin);
	const canSubmit = $derived(!submitting && name.trim().length > 0);

	// Mirrors the Vue source: only send a track_filters_json object for the
	// custom selection, and drop null/undefined keys from it; otherwise null.
	function buildTrackFilters(): TrackFilters | null {
		if (trackSelection !== 'custom') return null;
		return Object.fromEntries(
			Object.entries(filters).filter(([, v]) => v !== null && v !== undefined)
		) as TrackFilters;
	}

	async function submit(event: Event): Promise<void> {
		event.preventDefault();
		// Built-ins are read-only — no save path (Enter is a no-op too).
		if (isBuiltin || !canSubmit) return;
		submitting = true;
		error = null;
		try {
			let result: RipPresetView;
			if (editing && preset) {
				// Custom edit: no media_type (immutable after create).
				result = await updateRipPreset(preset.id, {
					name,
					track_selection: trackSelection,
					identification_mode: identificationMode,
					output_mode: outputMode,
					track_filters_json: buildTrackFilters()
				});
			} else {
				result = await createRipPreset({
					name,
					media_type: mediaType,
					track_selection: trackSelection,
					identification_mode: identificationMode,
					output_mode: outputMode,
					track_filters_json: buildTrackFilters()
				});
			}
			onsaved(result);
		} catch (e) {
			error = e instanceof Error ? e.message : 'Save failed';
		} finally {
			submitting = false;
		}
	}

	const labelClass = 'text-sm font-medium text-gray-700 dark:text-gray-300';
	const inputClass =
		'mt-1 w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 disabled:cursor-not-allowed disabled:opacity-50 dark:border-gray-600 dark:bg-gray-800 dark:text-white';
</script>

<form class="space-y-4" onsubmit={submit}>
	<!-- Title lives in the slide-over panel header (SessionsArea) -->
	{#if isBuiltin}
		<div
			class="rounded-md border border-amber-300 bg-amber-50 px-3 py-2 text-sm text-amber-800 dark:border-amber-700/50 dark:bg-amber-900/20 dark:text-amber-300"
			data-testid="preset-builtin-note"
			role="status"
		>
			This is a built-in preset and can't be edited. Clone it to make an editable copy.
		</div>
	{/if}

	{#if error}
		<p class="text-sm text-red-600 dark:text-red-400" data-testid="preset-error">{error}</p>
	{/if}

	<div>
		<label class={labelClass} for="preset-name">Name</label>
		<input
			id="preset-name"
			data-testid="preset-name"
			type="text"
			required
			bind:value={name}
			disabled={submitting || isBuiltin}
			class={inputClass}
		/>
	</div>

	<div>
		<label class={labelClass} for="preset-media-type">Media type</label>
		<select
			id="preset-media-type"
			data-testid="preset-media-type"
			bind:value={mediaType}
			disabled={editing}
			class={inputClass}
		>
			<option value="movie">Movie</option>
			<option value="tv">TV</option>
			<option value="music">Music</option>
			<option value="data">Data</option>
			<option value="iso">ISO</option>
		</select>
	</div>

	<div>
		<label class={labelClass} for="preset-track-selection">Track selection</label>
		<select
			id="preset-track-selection"
			data-testid="preset-track-selection"
			bind:value={trackSelection}
			disabled={isBuiltin}
			class={inputClass}
		>
			<option value="main_feature">Main feature (longest ≥ 45 min)</option>
			<option value="all_tracks">All tracks (≥ 60 s)</option>
			<option value="archive">Archive (every track)</option>
			<option value="custom">Custom</option>
		</select>
	</div>

	<div>
		<label class={labelClass} for="preset-identification-mode">Identification mode</label>
		<select
			id="preset-identification-mode"
			data-testid="preset-identification-mode"
			bind:value={identificationMode}
			disabled={isBuiltin}
			class={inputClass}
		>
			<option value="required">Required</option>
			<option value="skip">Skip</option>
			<option value="deferred_placeholder">Deferred placeholder</option>
		</select>
	</div>

	<div>
		<label class={labelClass} for="preset-output-mode">Output mode</label>
		<select
			id="preset-output-mode"
			data-testid="preset-output-mode"
			bind:value={outputMode}
			disabled={isBuiltin}
			class={inputClass}
		>
			<option value="tracks">Tracks</option>
			<option value="iso">ISO</option>
			<option value="data_copy">Data copy</option>
		</select>
	</div>

	{#if showFilters}
		<TrackFiltersEditor value={filters} onchange={(v) => (filters = v)} />
	{/if}

	<div class="flex justify-end gap-3 pt-2">
		<button
			type="button"
			onclick={oncancel}
			disabled={submitting}
			class="rounded-lg px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-100 dark:text-gray-300 dark:hover:bg-gray-700"
		>
			{isBuiltin ? 'Close' : 'Cancel'}
		</button>
		{#if !isBuiltin}
			<button
				type="submit"
				disabled={!canSubmit}
				data-testid="preset-submit"
				class="rounded-lg px-4 py-2 text-sm font-medium confirm-btn-primary disabled:cursor-not-allowed disabled:opacity-50"
			>
				{submitting ? 'Saving...' : 'Save'}
			</button>
		{/if}
	</div>
</form>
