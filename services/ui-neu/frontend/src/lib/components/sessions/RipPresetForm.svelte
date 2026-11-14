<script lang="ts">
	// Ported from the removed Vue UI's RipPresetForm view. The Vue view was a
	// routed page; this is an inline (no-route) form driven by props. Field
	// wiring, the disabled rules, and the create / custom-edit / built-in
	// submit-body shapes follow the Vue source faithfully.
	import { createRipPreset, updateRipPreset } from '$lib/api/rip-presets';
	import { PresetSave } from '$lib/stores/preset-save.svelte';
	import type { EditorStatus } from '../../ui/editor-status';
	import TrackFiltersEditor from '../jobs/TrackFiltersEditor.svelte';
	import { trackFiltersBody, type TrackFilters } from '$lib/jobs/track-filters';
	import { errorId, focusFirstInvalid, invalidAttrs, nameErrors } from '$lib/utils/formValidation';
	import type { IdentificationMode, MediaType, OutputMode, RipPresetView, TrackSelection } from '$lib/types/api.gen';

	let {
		preset = null,
		onsaved,
		formId,
		onstatus
	}: {
		preset?: RipPresetView | null;
		onsaved: (p: RipPresetView) => void;
		/** The hosting EditorSidebar's footer owns the title and the buttons, and submits this form by id. */
		formId: string;
		/** Reports the save state to the hosting footer, whenever it changes. */
		onstatus?: (status: EditorStatus) => void;
	} = $props();

	const editing = $derived(!!preset);
	const isBuiltin = $derived(preset?.is_builtin ?? false);

	// Seed from the preset on edit, or the create-defaults otherwise.
	let name = $state(preset?.name ?? '');
	let mediaType = $state<MediaType>(preset?.media_type ?? 'movie');
	let trackSelection = $state<TrackSelection>(preset?.track_selection ?? 'main_feature');
	let identificationMode = $state<IdentificationMode>(preset?.identification_mode ?? 'required');
	let outputMode = $state<OutputMode>(preset?.output_mode ?? 'tracks');
	let filters = $state<TrackFilters>((preset?.track_filters_json as TrackFilters) ?? {});

	const save = new PresetSave();

	const NAME_ID = 'preset-name';

	const showFilters = $derived(trackSelection === 'custom' && !isBuiltin);
	// Marks show from the first Save on, and each clears once its field is valid.
	let attempted = $state(false);
	const errors = $derived(attempted ? nameErrors(NAME_ID, name) : {});

	$effect(() => {
		onstatus?.({ submitting: save.submitting, note: '' });
	});

	function savePreset(): Promise<RipPresetView> {
		// Custom edit: no media_type (immutable after create).
		if (editing && preset)
			return updateRipPreset(preset.id, {
				name,
				track_selection: trackSelection,
				identification_mode: identificationMode,
				output_mode: outputMode,
				track_filters_json: trackFiltersBody(trackSelection, filters)
			});
		return createRipPreset({
			name,
			media_type: mediaType,
			track_selection: trackSelection,
			identification_mode: identificationMode,
			output_mode: outputMode,
			track_filters_json: trackFiltersBody(trackSelection, filters)
		});
	}

	async function submit(event: Event): Promise<void> {
		event.preventDefault();
		// Built-ins are read-only — no save path (Enter is a no-op too).
		if (isBuiltin || save.submitting) return;
		attempted = true;
		if (await focusFirstInvalid(nameErrors(NAME_ID, name), [NAME_ID])) return;
		await save.run(savePreset, (p) => onsaved(p));
	}

	// the old shared input-class constants are gone: inputs live in .field
	// wrappers now, styled by field.css's descendant rule.
</script>

<form id={formId} class="stack rip-preset-form" onsubmit={submit}>
	{#if isBuiltin}
		<div class="alert alert-warning" data-testid="preset-builtin-note" role="status">
			This is a built-in preset and can't be edited. Clone it to make an editable copy.
		</div>
	{/if}

	{#if save.error}
		<p class="field-error" data-testid="preset-error">{save.error}</p>
	{/if}

	<div class="field">
		<label class="field-label" for={NAME_ID}>Name</label>
		<input
			id={NAME_ID}
			data-testid="preset-name"
			type="text"
			bind:value={name}
			disabled={save.submitting || isBuiltin}
			{...invalidAttrs(NAME_ID, errors[NAME_ID])}
		/>
		{#if errors[NAME_ID]}<p class="field-error" id={errorId(NAME_ID)}>{errors[NAME_ID]}</p>{/if}
	</div>

	<label class="field">
		<span class="field-label">Media type</span>
		<select id="preset-media-type" data-testid="preset-media-type" bind:value={mediaType} disabled={editing}>
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
		<select id="preset-output-mode" data-testid="preset-output-mode" bind:value={outputMode} disabled={isBuiltin}>
			<option value="tracks">Tracks</option>
			<option value="iso">ISO</option>
			<option value="data_copy">Data copy</option>
			<option value="folder">Disc backup (folder)</option>
		</select>
	</label>

	{#if showFilters}
		<TrackFiltersEditor value={filters} onchange={(v) => (filters = v)} />
	{/if}
</form>
