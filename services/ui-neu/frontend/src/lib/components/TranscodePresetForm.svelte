<script lang="ts">
	// Ported from services/ui/src/views/TranscodePresetForm.vue, structured to
	// match the sibling RipPresetForm.svelte (T2a). Inline (no-route) form
	// driven by props. media_type is immutable on edit; built-in presets are
	// name-only; nullable fields submit `value || null`. `encoder` is one
	// arm_common.encoders catalog id. preset_json is not exposed.
	import { onMount } from 'svelte';
	import { createTranscodePreset, updateTranscodePreset } from '$lib/api/transcodePresets';
	import { fetchGpus } from '$lib/api/gpus';
	import { ENCODER_OPTIONS, PRESET_ENCODER_ID } from '$lib/utils/encoders';
	import type {
		ContainerFormat,
		MediaType,
		TranscodePresetView,
		TranscodeTool
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
	let encoder = $state<string>(preset?.encoder ?? PRESET_ENCODER_ID);


	// Live inventory context (G-30 awareness): what silicon "Any" will actually
	// use, shown where hardware intent is expressed. Soft-fails to no hint.
	let gpuHint = $state<string | null>(null);
	onMount(async () => {
		try {
			const gpus = await fetchGpus();
			if (gpus.length === 0) {
				gpuHint = 'This host has no GPUs configured; hardware presets fall back to CPU.';
				return;
			}
			const parts = gpus.map((g) => {
				const dev = g.device_path.split('/').pop() ?? g.device_path;
				const base = `${g.vendor.toUpperCase()} ${dev} (${g.encoder_kinds.join(', ')})`;
				return g.enabled ? base : `${base} disabled`;
			});
			gpuHint = `This host: ${parts.join(' + ')}`;
		} catch {
			gpuHint = null;
		}
	});
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
					encoder,
					extra_args: extraArgs || null
				});
			} else {
				result = await createTranscodePreset({
					name,
					media_type: mediaType,
					tool,
					preset_ref: presetRef || null,
					container,
					encoder,
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
		<span class="field-label">Encoder</span>
		<select
			id="tp-encoder"
			data-testid="tp-encoder"
			bind:value={encoder}
			disabled={isBuiltin}
		>
			{#each ENCODER_OPTIONS as opt (opt.id)}
				<option value={opt.id}>{opt.label}</option>
			{/each}
		</select>
		{#if gpuHint}
			<span class="transcode-preset-form-gpu-hint" data-testid="tp-gpu-hint">{gpuHint}</span>
		{/if}
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

	.transcode-preset-form-gpu-hint {
		display: block;
		margin-top: 0.25rem;
		font-size: 0.75rem;
		color: var(--color-text-muted);
	}
</style>
