<script lang="ts">
	// Ported from services/ui/src/views/TranscodePresetForm.vue, structured to
	// match the sibling RipPresetForm.svelte (T2a). Inline (no-route) form
	// driven by props. media_type is immutable on edit; built-in presets are
	// name-only; nullable fields submit `value || null`. Adds a `codec` select
	// (beyond the Vue form, per the T2b spec). preset_json is not exposed.
	import { createTranscodePreset, updateTranscodePreset } from '$lib/api/transcodePresets';
	import type {
		ContainerFormat,
		HwPreference,
		MediaType,
		TranscodePresetView,
		TranscodeTool,
		VideoCodec
	} from '$lib/types/api.gen';

	let {
		preset = null,
		onsaved,
		oncancel
	}: {
		preset?: TranscodePresetView | null;
		onsaved: (p: TranscodePresetView) => void;
		oncancel: () => void;
	} = $props();

	const editing = $derived(!!preset);
	const isBuiltin = $derived(preset?.is_builtin ?? false);

	let name = $state(preset?.name ?? '');
	let mediaType = $state<MediaType>(preset?.media_type ?? 'movie');
	let tool = $state<TranscodeTool>(preset?.tool ?? 'handbrake');
	let presetRef = $state(preset?.preset_ref ?? '');
	let container = $state<ContainerFormat>(preset?.container ?? 'mkv');
	// '' represents "no codec" (null). VideoCodec never includes ''.
	let codec = $state<VideoCodec | ''>(preset?.codec ?? '');
	let hwPreference = $state<HwPreference | ''>(preset?.hw_preference ?? '');
	let extraArgs = $state(preset?.extra_args ?? '');

	let submitting = $state(false);
	let error = $state<string | null>(null);

	const canSubmit = $derived(!submitting && name.trim().length > 0);

	async function submit(event: Event): Promise<void> {
		event.preventDefault();
		// Built-ins are read-only — no save path (Enter is a no-op too).
		if (isBuiltin || !canSubmit) return;
		submitting = true;
		error = null;
		try {
			let result: TranscodePresetView;
			if (editing && preset) {
				// Custom edit: no media_type (immutable after create).
				result = await updateTranscodePreset(preset.id, {
					name,
					tool,
					preset_ref: presetRef || null,
					container,
					codec: codec || null,
					hw_preference: hwPreference || null,
					extra_args: extraArgs || null
				});
			} else {
				result = await createTranscodePreset({
					name,
					media_type: mediaType,
					tool,
					preset_ref: presetRef || null,
					container,
					codec: codec || null,
					hw_preference: hwPreference || null,
					extra_args: extraArgs || null
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

<form class="stack transcode-preset-form" onsubmit={submit}>
	<h3 class="transcode-preset-form-title">
		{isBuiltin ? 'View transcode preset' : editing ? 'Edit transcode preset' : 'New transcode preset'}
	</h3>

	{#if isBuiltin}
		<div
			class="alert alert-warning"
			data-testid="tp-builtin-note"
			role="status"
		>
			This is a built-in preset and can't be edited. Clone it to make an editable copy.
		</div>
	{/if}

	{#if error}
		<p class="field-error" data-testid="tp-error">{error}</p>
	{/if}

	<label class="field">
		<span class="field-label">Name</span>
		<input
			id="tp-name"
			data-testid="tp-name"
			type="text"
			required
			bind:value={name}
			disabled={submitting || isBuiltin}
		/>
	</label>

	<label class="field">
		<span class="field-label">Media type</span>
		<select
			id="tp-media-type"
			data-testid="tp-media-type"
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
		<span class="field-label">Tool</span>
		<select
			id="tp-tool"
			data-testid="tp-tool"
			bind:value={tool}
			disabled={isBuiltin}
		>
			<option value="handbrake">HandBrake</option>
			<option value="abcde">abcde</option>
			<option value="none">None</option>
		</select>
	</label>

	<label class="field">
		<span class="field-label">Preset ref (HandBrake/abcde profile name)</span>
		<input
			id="tp-preset-ref"
			data-testid="tp-preset-ref"
			type="text"
			bind:value={presetRef}
			disabled={isBuiltin}
		/>
	</label>

	<label class="field">
		<span class="field-label">Container</span>
		<select
			id="tp-container"
			data-testid="tp-container"
			bind:value={container}
			disabled={isBuiltin}
		>
			<option value="mkv">MKV</option>
			<option value="mp4">MP4</option>
			<option value="webm">WebM</option>
			<option value="flac">FLAC</option>
			<option value="mp3">MP3</option>
			<option value="ogg">OGG</option>
			<option value="iso">ISO</option>
			<option value="none">None</option>
		</select>
	</label>

	<label class="field">
		<span class="field-label">Codec</span>
		<select
			id="tp-codec"
			data-testid="tp-codec"
			bind:value={codec}
			disabled={isBuiltin}
		>
			<option value="">(default)</option>
			<option value="h264">H.264</option>
			<option value="h265">H.265</option>
			<option value="av1">AV1</option>
		</select>
	</label>

	<label class="field">
		<span class="field-label">Hardware preference</span>
		<select
			id="tp-hw-preference"
			data-testid="tp-hw-preference"
			bind:value={hwPreference}
			disabled={isBuiltin}
		>
			<option value="">(unset)</option>
			<option value="cpu_only">CPU only</option>
			<option value="any">Any</option>
		</select>
	</label>

	<label class="field">
		<span class="field-label">Extra args</span>
		<input
			id="tp-extra-args"
			data-testid="tp-extra-args"
			type="text"
			bind:value={extraArgs}
			disabled={isBuiltin}
		/>
	</label>

	<div class="transcode-preset-form-actions">
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
				data-testid="tp-submit"
				class="btn btn-primary"
			>
				{submitting ? 'Saving...' : 'Save'}
			</button>
		{/if}
	</div>
</form>

<style>
	.transcode-preset-form-title { font-size: 1.125rem; line-height: 1.75rem; font-weight: 600; color: var(--color-text); }
	.transcode-preset-form-actions { display: flex; justify-content: flex-end; gap: 0.75rem; padding-top: 0.5rem; }
</style>
