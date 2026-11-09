<script lang="ts">
	// Ported from the removed Vue UI's TranscodePresetForm view, structured to
	// match the sibling RipPresetForm.svelte (T2a). Inline (no-route) form
	// driven by props. media_type is immutable on edit; built-in presets are
	// name-only; nullable fields submit `value || null`. `encoder` is one
	// arm_common.encoders catalog id. preset_json is not exposed.
	import { onMount } from 'svelte';
	import { createTranscodePreset, updateTranscodePreset } from '$lib/api/transcodePresets';
	import { encodersStore, PRESET_ENCODER_ID } from '$lib/stores/encoders.svelte';
	import { PresetSave } from '$lib/stores/presetSave.svelte';
	import { encoderGroups } from '$lib/utils/encoder-groups';
	import type { ContainerFormat, MediaType, TranscodePresetView, TranscodeTool } from '$lib/types/api.gen';

	// A HandBrake preset name that names a hardware encoder (a common
	// convention in preset libraries) does nothing on its own. HandBrake
	// only attaches a GPU when the Encoder field above asks for one.
	const HARDWARE_HINT_PATTERN = /QSV|NVENC|VCN|VCE/i;

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

	// Availability-aware encoder catalog (GET /api/encoders, cached by the
	// shared store), in catalog order. Refreshed on open: availability moves
	// with GPU probes and the enabled switches.
	onMount(() => {
		encodersStore.refresh();
	});
	let encoders = $derived(encodersStore.list);
	let encodersLoading = $derived(encodersStore.loading);
	let encodersError = $derived(encodersStore.error);

	let optgroups = $derived(encoderGroups(encoders));

	// abcde/none presets can't carry a codec encoder (only handbrake presets
	// can); force it back to the tool's own encoder so saving never 422s.
	let encoderLocked = $derived(tool === 'abcde' || tool === 'none');
	$effect(() => {
		if (encoderLocked && !isBuiltin) encoder = PRESET_ENCODER_ID;
	});

	let selectedEncoder = $derived(encoders.find((e) => e.id === encoder));
	// vaapi_* encoders run over ffmpeg directly; the HandBrake preset name
	// plays no part, and extra_args are ffmpeg CLI flags, not HandBrake ones.
	let usesFfmpegVaapi = $derived(selectedEncoder?.engine === 'ffmpeg_vaapi');
	// That ffmpeg path copies the source audio, which WebM cannot carry, so
	// it writes MKV or MP4 only (the API refuses the pairing with a 422).
	$effect(() => {
		if (usesFfmpegVaapi && container === 'webm' && !isBuiltin) container = 'mkv';
	});
	// An any_* encoder may resolve to an AMD device at claim time, which runs
	// ffmpeg instead of HandBrake.
	let anyGpuSelected = $derived(selectedEncoder?.kind === 'any');

	let encoderHint = $derived(
		encoder === PRESET_ENCODER_ID && HARDWARE_HINT_PATTERN.test(presetRef)
			? 'This HandBrake preset uses a hardware encoder; choose the matching encoder above or ARM will not attach a GPU.'
			: null
	);

	let extraArgs = $state(preset?.extra_args ?? '');

	const save = new PresetSave();

	const canSubmit = $derived(!save.submitting && name.trim().length > 0);

	function savePreset(): Promise<TranscodePresetView> {
		// Custom edit: no media_type (immutable after create).
		if (editing && preset)
			return updateTranscodePreset(preset.id, {
				name,
				tool,
				preset_ref: presetRef || null,
				container,
				encoder,
				extra_args: extraArgs || null
			});
		return createTranscodePreset({
			name,
			media_type: mediaType,
			tool,
			preset_ref: presetRef || null,
			container,
			encoder,
			extra_args: extraArgs || null
		});
	}

	async function submit(event: Event): Promise<void> {
		event.preventDefault();
		// Built-ins are read-only — no save path (Enter is a no-op too).
		if (isBuiltin || !canSubmit) return;
		await save.run(savePreset, (p) => onsaved(p));
	}

	// the old shared input-class constants are gone: inputs live in .field
	// wrappers now, styled by field.css's descendant rule.
</script>

<form class="stack transcode-preset-form" onsubmit={submit}>
	<h3 class="transcode-preset-form-title">
		{isBuiltin ? 'View transcode preset' : editing ? 'Edit transcode preset' : 'New transcode preset'}
	</h3>

	{#if isBuiltin}
		<div class="alert alert-warning" data-testid="tp-builtin-note" role="status">
			This is a built-in preset and can't be edited. Clone it to make an editable copy.
		</div>
	{/if}

	{#if save.error}
		<p class="field-error" data-testid="tp-error">{save.error}</p>
	{/if}

	<label class="field">
		<span class="field-label">Name</span>
		<input
			id="tp-name"
			data-testid="tp-name"
			type="text"
			required
			bind:value={name}
			disabled={save.submitting || isBuiltin}
		/>
	</label>

	<label class="field">
		<span class="field-label">Media type</span>
		<select id="tp-media-type" data-testid="tp-media-type" bind:value={mediaType} disabled={editing}>
			<option value="movie">Movie</option>
			<option value="tv">TV</option>
			<option value="music">Music</option>
			<option value="data">Data</option>
			<option value="iso">ISO</option>
		</select>
	</label>

	<label class="field">
		<span class="field-label">Tool</span>
		<select id="tp-tool" data-testid="tp-tool" bind:value={tool} disabled={isBuiltin}>
			<option value="handbrake">HandBrake</option>
			<option value="abcde">abcde</option>
			<option value="none">None</option>
		</select>
	</label>

	<label class="field">
		<span class="field-label">Preset ref (HandBrake/abcde profile name)</span>
		<input id="tp-preset-ref" data-testid="tp-preset-ref" type="text" bind:value={presetRef} disabled={isBuiltin} />
		{#if usesFfmpegVaapi}
			<p class="field-help" data-testid="tp-preset-ref-note">Not used by this encoder.</p>
		{/if}
	</label>

	<label class="field">
		<span class="field-label">Container</span>
		<select id="tp-container" data-testid="tp-container" bind:value={container} disabled={isBuiltin}>
			<option value="mkv">MKV</option>
			<option value="mp4">MP4</option>
			<option value="webm" disabled={usesFfmpegVaapi}>WebM</option>
			<option value="flac">FLAC</option>
			<option value="mp3">MP3</option>
			<option value="ogg">OGG</option>
			<option value="iso">ISO</option>
			<option value="none">None</option>
		</select>
		{#if usesFfmpegVaapi}
			<p class="field-help" data-testid="tp-container-vaapi-note">AMD VAAPI encoders write MKV or MP4.</p>
		{/if}
	</label>

	<label class="field">
		<span class="field-label">Encoder</span>
		<select
			id="tp-encoder"
			data-testid="tp-encoder"
			bind:value={encoder}
			disabled={isBuiltin || encoderLocked || encodersLoading}
		>
			{#if encodersLoading}
				<option value={encoder} disabled>Loading encoders...</option>
			{:else if encoders.length === 0}
				<option value={encoder}>{encoder}</option>
			{:else}
				{#each optgroups as grp (grp.group)}
					<optgroup label={grp.label}>
						{#each grp.encoders as enc (enc.id)}
							<option value={enc.id} disabled={!enc.available} title={enc.reason ?? undefined}>
								{enc.label}{enc.reason ? ` (${enc.reason})` : ''}
							</option>
						{/each}
					</optgroup>
				{/each}
			{/if}
		</select>
		{#if encodersError}
			<p class="field-error" data-testid="tp-encoder-error">Could not load encoders; the current encoder is kept.</p>
		{/if}
		{#if anyGpuSelected}
			<p class="field-help" data-testid="tp-encoder-any-note">
				HandBrake preset settings (scaling, filters, audio) apply on CPU, NVENC and QSV, but not when the job runs on an
				AMD (VAAPI) device.
			</p>
		{/if}
		{#if encoderHint}
			<p class="field-help" data-testid="tp-encoder-hint">{encoderHint}</p>
		{/if}
	</label>

	<label class="field">
		<span class="field-label">{usesFfmpegVaapi ? 'ffmpeg arguments' : 'Extra args'}</span>
		<input id="tp-extra-args" data-testid="tp-extra-args" type="text" bind:value={extraArgs} disabled={isBuiltin} />
	</label>

	<div class="transcode-preset-form-actions">
		<button type="button" onclick={oncancel} disabled={save.submitting} class="btn btn-ghost">
			{isBuiltin ? 'Close' : 'Cancel'}
		</button>
		{#if !isBuiltin}
			<button type="submit" disabled={!canSubmit} data-testid="tp-submit" class="btn btn-primary">
				{save.submitting ? 'Saving...' : 'Save'}
			</button>
		{/if}
	</div>
</form>

<style>
	.transcode-preset-form-title {
		font-size: 1.125rem;
		line-height: 1.75rem;
		font-weight: 600;
		color: var(--color-text);
	}
	.transcode-preset-form-actions {
		display: flex;
		justify-content: flex-end;
		gap: 0.75rem;
		padding-top: 0.5rem;
	}
</style>
