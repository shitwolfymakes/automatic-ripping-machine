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
		if (!canSubmit) return;
		submitting = true;
		error = null;
		try {
			let result: TranscodePresetView;
			if (editing && preset) {
				if (isBuiltin) {
					result = await updateTranscodePreset(preset.id, { name });
				} else {
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
				}
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

	const labelClass = 'text-sm font-medium text-gray-700 dark:text-gray-300';
	const inputClass =
		'mt-1 w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 disabled:cursor-not-allowed disabled:opacity-50 dark:border-gray-600 dark:bg-gray-800 dark:text-white';
</script>

<form class="space-y-4" onsubmit={submit}>
	<h3 class="text-lg font-semibold text-gray-900 dark:text-white">
		{editing ? 'Edit transcode preset' : 'New transcode preset'}
	</h3>

	{#if isBuiltin}
		<p class="text-sm text-gray-500 dark:text-gray-400" data-testid="tp-builtin-note">
			Built-in preset - only the name is editable.
		</p>
	{/if}

	{#if error}
		<p class="text-sm text-red-600 dark:text-red-400" data-testid="tp-error">{error}</p>
	{/if}

	<div>
		<label class={labelClass} for="tp-name">Name</label>
		<input
			id="tp-name"
			data-testid="tp-name"
			type="text"
			required
			bind:value={name}
			disabled={submitting}
			class={inputClass}
		/>
	</div>

	<div>
		<label class={labelClass} for="tp-media-type">Media type</label>
		<select
			id="tp-media-type"
			data-testid="tp-media-type"
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
		<label class={labelClass} for="tp-tool">Tool</label>
		<select
			id="tp-tool"
			data-testid="tp-tool"
			bind:value={tool}
			disabled={isBuiltin}
			class={inputClass}
		>
			<option value="handbrake">HandBrake</option>
			<option value="abcde">abcde</option>
			<option value="none">None</option>
		</select>
	</div>

	<div>
		<label class={labelClass} for="tp-preset-ref">Preset ref (HandBrake/abcde profile name)</label>
		<input
			id="tp-preset-ref"
			data-testid="tp-preset-ref"
			type="text"
			bind:value={presetRef}
			disabled={isBuiltin}
			class={inputClass}
		/>
	</div>

	<div>
		<label class={labelClass} for="tp-container">Container</label>
		<select
			id="tp-container"
			data-testid="tp-container"
			bind:value={container}
			disabled={isBuiltin}
			class={inputClass}
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
	</div>

	<div>
		<label class={labelClass} for="tp-codec">Codec</label>
		<select
			id="tp-codec"
			data-testid="tp-codec"
			bind:value={codec}
			disabled={isBuiltin}
			class={inputClass}
		>
			<option value="">(default)</option>
			<option value="h264">H.264</option>
			<option value="h265">H.265</option>
			<option value="av1">AV1</option>
		</select>
	</div>

	<div>
		<label class={labelClass} for="tp-hw-preference">Hardware preference</label>
		<select
			id="tp-hw-preference"
			data-testid="tp-hw-preference"
			bind:value={hwPreference}
			disabled={isBuiltin}
			class={inputClass}
		>
			<option value="">(unset)</option>
			<option value="cpu_only">CPU only</option>
			<option value="any">Any</option>
		</select>
	</div>

	<div>
		<label class={labelClass} for="tp-extra-args">Extra args</label>
		<input
			id="tp-extra-args"
			data-testid="tp-extra-args"
			type="text"
			bind:value={extraArgs}
			disabled={isBuiltin}
			class={inputClass}
		/>
	</div>

	<div class="flex justify-end gap-3 pt-2">
		<button
			type="button"
			onclick={oncancel}
			disabled={submitting}
			class="rounded-lg px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-100 dark:text-gray-300 dark:hover:bg-gray-700"
		>
			Cancel
		</button>
		<button
			type="submit"
			disabled={!canSubmit}
			data-testid="tp-submit"
			class="rounded-lg px-4 py-2 text-sm font-medium confirm-btn-primary disabled:cursor-not-allowed disabled:opacity-50"
		>
			{submitting ? 'Saving...' : 'Save'}
		</button>
	</div>
</form>
