<script lang="ts">
	// Ported from services/ui/src/views/SessionForm.vue, structured like the
	// sibling RipPresetForm/TranscodePresetForm. Inline (no-route) form.
	// media_type immutable on edit; built-in is name-only. Loads rip + transcode
	// preset lists for the dropdowns, filtered to the form's media_type (the
	// backend requires preset.media_type == session.media_type). Live debounced
	// /preview under the template field. overrides_json is NEVER sent (a seeded
	// value must survive an edit untouched).
	import { onMount, onDestroy } from 'svelte';
	import { createSession, updateSession, previewTemplate } from '$lib/api/sessions';
	import { fetchRipPresets } from '$lib/api/ripPresets';
	import { fetchTranscodePresets } from '$lib/api/transcodePresets';
	import type {
		MediaType,
		RipPresetView,
		SessionView,
		TranscodePresetView
	} from '$lib/types/api.gen';

	let {
		session = null,
		onsaved,
		oncancel
	}: {
		session?: SessionView | null;
		onsaved: (s: SessionView) => void;
		oncancel: () => void;
	} = $props();

	const editing = $derived(!!session);
	const isBuiltin = $derived(session?.is_builtin ?? false);

	let name = $state(session?.name ?? '');
	let mediaType = $state<MediaType>(session?.media_type ?? 'movie');
	let ripPresetId = $state(session?.rip_preset_id ?? '');
	let transcodePresetId = $state(session?.transcode_preset_id ?? '');
	let template = $state(session?.output_path_template ?? '');

	let ripPresets = $state<RipPresetView[]>([]);
	let transcodePresets = $state<TranscodePresetView[]>([]);

	let submitting = $state(false);
	let error = $state<string | null>(null);

	let previewText = $state('');
	let previewError = $state<string | null>(null);
	let previewTimer: ReturnType<typeof setTimeout> | null = null;

	const ripOptions = $derived(ripPresets.filter((p) => p.media_type === mediaType));
	const transcodeOptions = $derived(transcodePresets.filter((p) => p.media_type === mediaType));
	const canSubmit = $derived(!submitting && name.trim().length > 0 && ripPresetId.length > 0);

	onMount(async () => {
		[ripPresets, transcodePresets] = await Promise.all([fetchRipPresets(), fetchTranscodePresets()]);
		if (!ripPresetId) ripPresetId = ripOptions[0]?.id ?? '';
		runPreview();
	});

	onDestroy(() => {
		if (previewTimer !== null) clearTimeout(previewTimer);
	});

	// When media_type changes (create mode only — disabled on edit), drop any
	// now-invalid preset selection so submit can't 400 on a media_type mismatch.
	function onMediaTypeChange(): void {
		if (!ripPresets.some((p) => p.media_type === mediaType && p.id === ripPresetId)) {
			ripPresetId = ripOptions[0]?.id ?? '';
		}
		if (!transcodePresets.some((p) => p.media_type === mediaType && p.id === transcodePresetId))
			transcodePresetId = '';
		runPreview();
	}

	function schedulePreview(): void {
		if (previewTimer !== null) clearTimeout(previewTimer);
		previewTimer = setTimeout(runPreview, 300);
	}

	async function runPreview(): Promise<void> {
		if (!template) {
			previewText = '';
			previewError = null;
			return;
		}
		try {
			const resp = await previewTemplate({
				template,
				media_type: mediaType,
				has_transcode_preset: Boolean(transcodePresetId)
			});
			previewText = resp.expansion;
			previewError = null;
		} catch (e) {
			previewText = '';
			previewError = e instanceof Error ? e.message : 'Preview failed';
		}
	}

	async function submit(event: Event): Promise<void> {
		event.preventDefault();
		if (!canSubmit) return;
		submitting = true;
		error = null;
		try {
			let result: SessionView;
			if (editing && session) {
				if (isBuiltin) {
					result = await updateSession(session.id, { name });
				} else {
					// Custom edit: no media_type (immutable), no overrides_json (preserve).
					result = await updateSession(session.id, {
						name,
						rip_preset_id: ripPresetId,
						transcode_preset_id: transcodePresetId || null,
						output_path_template: template
					});
				}
			} else {
				result = await createSession({
					name,
					media_type: mediaType,
					rip_preset_id: ripPresetId,
					transcode_preset_id: transcodePresetId || null,
					output_path_template: template
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
		{editing ? 'Edit session' : 'New session'}
	</h3>

	{#if isBuiltin}
		<p class="text-sm text-gray-500 dark:text-gray-400" data-testid="session-builtin-note">
			Built-in preset - only the name is editable. Clone it to customise.
		</p>
	{/if}

	{#if error}
		<p class="text-sm text-red-600 dark:text-red-400" data-testid="session-error">{error}</p>
	{/if}

	<div>
		<label class={labelClass} for="session-name">Name</label>
		<input
			id="session-name"
			data-testid="session-name"
			type="text"
			required
			bind:value={name}
			disabled={submitting}
			class={inputClass}
		/>
	</div>

	<div>
		<label class={labelClass} for="session-media-type">Media type</label>
		<select
			id="session-media-type"
			data-testid="session-media-type"
			bind:value={mediaType}
			onchange={onMediaTypeChange}
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
		<label class={labelClass} for="session-rip-preset">Rip preset</label>
		<select
			id="session-rip-preset"
			data-testid="session-rip-preset"
			bind:value={ripPresetId}
			disabled={isBuiltin}
			required
			class={inputClass}
		>
			{#each ripOptions as p (p.id)}
				<option value={p.id}>{p.name}</option>
			{/each}
		</select>
	</div>

	<div>
		<label class={labelClass} for="session-transcode-preset">Transcode preset (optional)</label>
		<select
			id="session-transcode-preset"
			data-testid="session-transcode-preset"
			bind:value={transcodePresetId}
			onchange={schedulePreview}
			disabled={isBuiltin}
			class={inputClass}
		>
			<option value="">- none -</option>
			{#each transcodeOptions as p (p.id)}
				<option value={p.id}>{p.name}</option>
			{/each}
		</select>
	</div>

	<div>
		<label class={labelClass} for="session-template">Output path template</label>
		<input
			id="session-template"
			data-testid="session-template"
			type="text"
			required
			bind:value={template}
			oninput={schedulePreview}
			disabled={isBuiltin}
			class={inputClass}
		/>
		{#if previewError}
			<p class="mt-1 rounded-md border border-red-300 bg-red-50 px-2.5 py-1.5 font-mono text-xs text-red-700 dark:border-red-700 dark:bg-red-900/20 dark:text-red-400" data-testid="session-preview-error">
				{previewError}
			</p>
		{:else if previewText}
			<p class="mt-1 rounded-md border-l-2 border-primary bg-primary/5 px-2.5 py-1.5 font-mono text-xs text-primary-text dark:text-primary-text-dark" data-testid="session-preview">
				▸ {previewText}
			</p>
		{/if}
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
			data-testid="session-submit"
			class="rounded-lg px-4 py-2 text-sm font-medium confirm-btn-primary disabled:cursor-not-allowed disabled:opacity-50"
		>
			{submitting ? 'Saving...' : 'Save'}
		</button>
	</div>
</form>
