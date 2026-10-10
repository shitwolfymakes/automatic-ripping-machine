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

	// the old shared input-class constants are gone: inputs live in .field
	// wrappers now, styled by field.css's descendant rule.
</script>

<form class="stack rip-preset-form" onsubmit={submit}>
	<h3 class="rip-preset-form-title">
		{isBuiltin ? 'View rip preset' : editing ? 'Edit rip preset' : 'New rip preset'}
	</h3>

	{#if isBuiltin}
		<div
			class="alert alert-warning"
			data-testid="preset-builtin-note"
			role="status"
		>
			This is a built-in preset and can't be edited. Clone it to make an editable copy.
		</div>
	{/if}

	{#if error}
		<p class="field-error" data-testid="preset-error">{error}</p>
	{/if}

	<label class="field">
		<span class="field-label">Name</span>
		<input
			id="preset-name"
			data-testid="preset-name"
			type="text"
			required
			bind:value={name}
			disabled={submitting || isBuiltin}
		/>
	</label>

	<label class="field">
		<span class="field-label">Media type</span>
		<select
			id="preset-media-type"
			data-testid="preset-media-type"
			bind:value={mediaType}
			disabled={editing}
		>
			<option value="movie">Movie</option>
			<option value="tv">TV</option>
			<option value="music">Music</option>
			<option value="data">Data</option>
			<option value="iso">ISO</option>
		</select>
	</label>

	<label class="field">
		<span class="field-label">Track selection</span>
		<select
			id="preset-track-selection"
			data-testid="preset-track-selection"
			bind:value={trackSelection}
			disabled={isBuiltin}
		>
			<option value="main_feature">Main feature (longest >= 45 min)</option>
			<option value="all_tracks">All tracks (>= 60 s)</option>
			<option value="archive">Archive (every track)</option>
			<option value="custom">Custom</option>
		</select>
	</label>

	<label class="field">
		<span class="field-label">Identification mode</span>
		<select
			id="preset-identification-mode"
			data-testid="preset-identification-mode"
			bind:value={identificationMode}
			disabled={isBuiltin}
		>
			<option value="required">Required</option>
			<option value="skip">Skip</option>
			<option value="deferred_placeholder">Deferred placeholder</option>
		</select>
	</label>

	<label class="field">
		<span class="field-label">Output mode</span>
		<select
			id="preset-output-mode"
			data-testid="preset-output-mode"
			bind:value={outputMode}
			disabled={isBuiltin}
		>
			<option value="tracks">Tracks</option>
			<option value="iso">ISO</option>
			<option value="data_copy">Data copy</option>
		</select>
	</label>

	{#if showFilters}
		<TrackFiltersEditor value={filters} onchange={(v) => (filters = v)} />
	{/if}

	<div class="rip-preset-form-actions">
		<button
			type="button"
			onclick={oncancel}
			disabled={submitting}
			class="btn btn-ghost"
		>
			{isBuiltin ? 'Close' : 'Cancel'}
		</button>
		{#if !isBuiltin}
			<button
				type="submit"
				disabled={!canSubmit}
				data-testid="preset-submit"
				class="btn btn-primary"
			>
				{submitting ? 'Saving...' : 'Save'}
			</button>
		{/if}
	</div>
</form>

<style>
	.rip-preset-form-title { font-size: 1.125rem; line-height: 1.75rem; font-weight: 600; color: var(--color-text); }
	.rip-preset-form-actions { display: flex; justify-content: flex-end; gap: 0.75rem; padding-top: 0.5rem; }
</style>
