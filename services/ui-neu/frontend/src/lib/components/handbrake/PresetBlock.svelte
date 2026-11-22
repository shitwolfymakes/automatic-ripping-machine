<script lang="ts">
	// The preset sidebar's always-visible block: name, media type, tool,
	// container, encoder, base preset and extra args. Controlled: each change
	// goes to onfield and the sidebar applies it to its draft. media_type is
	// immutable on edit; movie and TV both show as Video, since a preset of
	// either fits sessions of either. `encoder` is one arm_common.encoders catalog id.
	import { onMount } from 'svelte';
	import { encodersStore, PRESET_ENCODER_ID } from '$lib/stores/encoders.svelte';
	import { encoderGroups } from '$lib/utils/encoder-groups';
	import { PRESET_NAME_ID, presetBlockView } from '$lib/handbrake/panelView';
	import { CLEARED_NOTE, isVaapiEncoder, type Draft, type PresetField } from '$lib/handbrake/sidebarModel';
	import { presetBlockMessages } from '$lib/handbrake/issuePlacement';
	import { errorId, invalidAttrs, type FieldErrors } from '$lib/utils/formValidation';
	import type { SettingIssue } from '$lib/types/api.gen';
	import Glyph from '$lib/components/Glyph.svelte';
	import { OFFICIAL_PRESETS_URL } from '$lib/handbrake/docLinks';

	interface Props {
		draft: Draft;
		readonly: boolean;
		editing: boolean;
		/** HandBrake's built-in preset names, or null while no schema is loaded. */
		builtinNames: string[] | null;
		issues: SettingIssue[];
		/** The sidebar's own checks on Save (a blank name), by input id; they win over a save issue on the same field. */
		errors?: FieldErrors;
		onfield: (field: PresetField, value: string) => void;
	}

	let { draft, readonly, editing, builtinNames, issues, errors = {}, onfield }: Props = $props();

	// Availability-aware encoder catalog (GET /api/encoders, cached by the
	// shared store), in catalog order. Refreshed on open: availability moves
	// with GPU probes and the enabled switches.
	onMount(() => {
		encodersStore.refresh();
	});
	const encoders = $derived(encodersStore.list);
	const optgroups = $derived(encoderGroups(encoders));

	// vaapi_* encoders run over ffmpeg directly; the HandBrake base preset plays
	// no part, and extra args are ffmpeg CLI flags, not HandBrake ones.
	const view = $derived(
		presetBlockView({
			draft,
			readonly,
			builtinNames,
			encodersLoading: encodersStore.loading,
			encoderCount: encoders.length,
			presetEncoderId: PRESET_ENCODER_ID
		})
	);
	const REF_ID = 'tp-preset-ref';
	// What each field shows under it: the sidebar's own check, else a save issue on that field.
	const messages = $derived({ ...presetBlockMessages(issues), ...errors });
	const aria = (id: string) => invalidAttrs(id, messages[id]);

	// A stored name this HandBrake build does not have stays listed, so it is not lost on save.
	function withStoredName(names: string[], stored: string | null): string[] {
		return stored && !names.includes(stored) ? [stored, ...names] : names;
	}

	function value(e: Event): string {
		return (e.currentTarget as HTMLInputElement | HTMLSelectElement).value;
	}

	// The ffmpeg path copies the source audio, which WebM cannot carry, so it
	// writes MKV or MP4 only (the API refuses the pairing with a 422).
	function onEncoder(e: Event) {
		const id = value(e);
		onfield('encoder', id);
		if (isVaapiEncoder(id) && draft.container === 'webm') onfield('container', 'mkv');
	}
</script>

<div class="preset-block">
	<div class="field preset-block-wide">
		<label class="field-label" for={PRESET_NAME_ID}>Name</label>
		<input
			id={PRESET_NAME_ID}
			data-testid="tp-name"
			type="text"
			value={draft.name}
			disabled={readonly}
			oninput={(e) => onfield('name', value(e))}
			{...aria(PRESET_NAME_ID)}
		/>
		{@render fieldError(PRESET_NAME_ID)}
	</div>

	<div class="field">
		<label class="field-label" for="tp-media-type">Media type</label>
		<select
			id="tp-media-type"
			data-testid="tp-media-type"
			value={draft.media_type === 'tv' ? 'movie' : draft.media_type}
			disabled={readonly || editing}
			onchange={(e) => onfield('media_type', value(e))}
			{...aria('tp-media-type')}
		>
			<!-- A movie or TV preset fits sessions of either, so one Video choice covers both. -->
			<option value="movie">Video</option>
			<option value="music">Music</option>
			<option value="data">Data</option>
			<option value="iso">ISO</option>
		</select>
		{@render fieldError('tp-media-type')}
	</div>

	<div class="field">
		<label class="field-label" for="tp-tool">Tool</label>
		<select
			id="tp-tool"
			data-testid="tp-tool"
			value={draft.tool}
			disabled={readonly}
			onchange={(e) => onfield('tool', value(e))}
			{...aria('tp-tool')}
		>
			<option value="handbrake">HandBrake</option>
			<option value="abcde">abcde</option>
			<option value="none">None</option>
		</select>
		{@render fieldError('tp-tool')}
	</div>

	<div class="field">
		<label class="field-label" for="tp-container">Container</label>
		<select
			id="tp-container"
			data-testid="tp-container"
			value={draft.container}
			disabled={readonly}
			onchange={(e) => onfield('container', value(e))}
			{...aria('tp-container')}
		>
			<option value="mkv">MKV</option>
			<option value="mp4">MP4</option>
			<option value="webm" disabled={view.usesFfmpegVaapi}>WebM</option>
			<option value="flac">FLAC</option>
			<option value="mp3">MP3</option>
			<option value="ogg">OGG</option>
			<option value="iso">ISO</option>
			<option value="none">None</option>
		</select>
		{@render fieldError('tp-container')}
		{#if view.usesFfmpegVaapi}
			<p class="field-help" data-testid="tp-container-vaapi-note">AMD VAAPI encoders write MKV or MP4.</p>
		{/if}
	</div>

	<div class="field">
		<label class="field-label" for="tp-encoder">Encoder</label>
		<select
			id="tp-encoder"
			data-testid="tp-encoder"
			value={draft.encoder}
			disabled={view.encoderDisabled}
			onchange={onEncoder}
			{...aria('tp-encoder')}
		>
			{#if view.encoderList === 'loading'}
				<option value={draft.encoder} disabled>Loading encoders...</option>
			{:else if view.encoderList === 'empty'}
				<option value={draft.encoder}>{draft.encoder}</option>
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
		{@render fieldError('tp-encoder')}
		{#if encodersStore.error}
			<p class="field-error" data-testid="tp-encoder-error">Could not load encoders; the current encoder is kept.</p>
		{/if}
		{#if view.encoderHint}
			<p class="field-help" data-testid="tp-encoder-hint">{view.encoderHint}</p>
		{/if}
	</div>

	<!-- The base preset is a select of HandBrake's built-ins once a schema is loaded; free text otherwise. -->
	{#if view.baseNames}
		<div class="field">
			{@render refLabel('Base preset')}
			<select
				id={REF_ID}
				data-testid="tp-preset-ref"
				value={draft.preset_ref ?? ''}
				disabled={readonly}
				onchange={(e) => onfield('preset_ref', value(e))}
				{...aria(REF_ID)}
			>
				<option value="">None (HandBrake defaults)</option>
				{#each withStoredName(view.baseNames, draft.preset_ref) as name (name)}
					<option value={name}>{name}</option>
				{/each}
			</select>
			{@render refNotes()}
		</div>
	{:else}
		<div class="field">
			{@render refLabel('Preset ref')}
			<input
				id={REF_ID}
				data-testid="tp-preset-ref"
				type="text"
				value={draft.preset_ref ?? ''}
				disabled={readonly}
				onchange={(e) => onfield('preset_ref', value(e))}
				{...aria(REF_ID)}
			/>
			{@render refNotes()}
		</div>
	{/if}

	<div class="field">
		<label class="field-label" for="tp-extra-args">{view.extraArgsLabel}</label>
		<input
			id="tp-extra-args"
			data-testid="tp-extra-args"
			type="text"
			value={draft.extra_args}
			disabled={readonly}
			oninput={(e) => onfield('extra_args', value(e))}
			{...aria('tp-extra-args')}
		/>
		{@render fieldError('tp-extra-args')}
		{#if view.showOverrideHelp}
			<p class="field-help">Flags here are added last and override the settings below.</p>
		{/if}
	</div>

	{#if view.showClearedNote}
		<p class="alert alert-warning preset-block-wide" role="status">{CLEARED_NOTE}</p>
	{/if}
</div>

{#snippet refLabel(text: string)}
	<span class="preset-block-label">
		<label class="field-label" for={REF_ID}>{text}</label>
		{#if view.showPresetsDocLink}
			<a
				class="preset-block-info"
				href={OFFICIAL_PRESETS_URL}
				target="_blank"
				rel="noopener noreferrer"
				title="HandBrake's official presets"
				aria-label="HandBrake docs: official presets"
				data-testid="tp-preset-ref-docs"
			>
				<Glyph name="info" class="h-3 w-3" />
			</a>
		{/if}
	</span>
{/snippet}

{#snippet refNotes()}
	{#if view.usesFfmpegVaapi}
		<p class="field-help" data-testid="tp-preset-ref-note">Not used by this encoder.</p>
	{/if}
	{@render fieldError(REF_ID)}
{/snippet}

{#snippet fieldError(id: string)}
	{#if messages[id]}<p class="field-error" id={errorId(id)} role="alert">{messages[id]}</p>{/if}
{/snippet}

<style>
	.preset-block {
		display: grid;
		grid-template-columns: repeat(2, minmax(0, 1fr));
		gap: 0.75rem 1rem;
	}
	.preset-block-wide {
		grid-column: 1 / -1;
	}
	.preset-block-label {
		display: inline-flex;
		align-items: center;
		gap: 0.375rem;
	}
	.preset-block-info {
		display: inline-flex;
		color: var(--color-text-faint);
	}
	.preset-block-info:hover {
		color: var(--color-text);
	}
</style>
