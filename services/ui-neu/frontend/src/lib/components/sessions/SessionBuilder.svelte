<script lang="ts">
	import type { MediaType, SessionView, RipPresetView, TranscodePresetView } from '$lib/types/api.gen';
	import type { JoinedSession } from './sessionsData.svelte';
	import { createSession, updateSession } from '$lib/api/sessions';
	import OutputPathField from './OutputPathField.svelte';

	interface Props {
		session?: JoinedSession | null;
		ripPresets: RipPresetView[];
		transcodePresets: TranscodePresetView[];
		oncreaterip: () => void;
		oncreatetranscode: () => void;
		onsaved: (s: SessionView) => void;
		oncancel: () => void;
		preselectRipId?: string;
		preselectTranscodeId?: string;
	}

	let {
		session,
		ripPresets,
		transcodePresets,
		oncreaterip,
		oncreatetranscode,
		onsaved,
		oncancel,
		preselectRipId,
		preselectTranscodeId,
	}: Props = $props();

	const MEDIA_TYPES: { value: MediaType; label: string }[] = [
		{ value: 'movie', label: 'Movie' },
		{ value: 'tv', label: 'TV' },
		{ value: 'music', label: 'Music' },
		{ value: 'data', label: 'Data' },
		{ value: 'iso', label: 'ISO' },
	];

	// Form state
	let name = $state(session?.name ?? '');
	let mediaType = $state<MediaType>(session?.media_type ?? 'movie');
	let ripId = $state(session?.rip_preset_id ?? '');
	let tcId = $state(session?.transcode_preset_id ?? '');
	let template = $state(session?.output_path_template ?? '');
	let overridesJson = $state(session?.overrides_json ? JSON.stringify(session.overrides_json, null, 2) : '');
	let jsonError = $state<string | null>(null);
	let submitError = $state<string | null>(null);
	let submitting = $state(false);

	// Derived options filtered by media type
	let ripOptions = $derived(ripPresets.filter((p) => p.media_type === mediaType));
	let tcOptions = $derived(transcodePresets.filter((p) => p.media_type === mediaType));

	// Apply preselect when parent sets them (after inline-create)
	$effect(() => {
		if (preselectRipId) {
			ripId = preselectRipId;
		}
	});
	$effect(() => {
		if (preselectTranscodeId) {
			tcId = preselectTranscodeId;
		}
	});

	const isEdit = $derived(!!session);
	// Built-in sessions are read-only — every field is locked, no save path.
	const readOnly = $derived(session?.is_builtin ?? false);
	const canSubmit = $derived(!readOnly && !!(name && ripId && template));

	function switchMediaType(mt: MediaType) {
		if (isEdit || readOnly) return; // immutable on edit / locked when built-in
		mediaType = mt;
		ripId = '';
		tcId = '';
	}

	function handleRipChange(e: Event) {
		const val = (e.target as HTMLSelectElement).value;
		if (val === '__create_rip__') {
			// revert the select and delegate to parent
			(e.target as HTMLSelectElement).value = ripId;
			oncreaterip();
		} else {
			ripId = val;
		}
	}

	function handleTcChange(e: Event) {
		const val = (e.target as HTMLSelectElement).value;
		if (val === '__create_tc__') {
			(e.target as HTMLSelectElement).value = tcId;
			oncreatetranscode();
		} else {
			tcId = val;
		}
	}

	async function handleSubmit(e: SubmitEvent) {
		e.preventDefault();
		if (readOnly) return; // built-ins can't be saved
		jsonError = null;
		submitError = null;

		let parsedOverrides: Record<string, unknown> | null = null;
		if (overridesJson.trim()) {
			try {
				parsedOverrides = JSON.parse(overridesJson);
			} catch {
				jsonError = 'Invalid JSON in overrides field';
				return;
			}
		}

		submitting = true;
		try {
			let result: SessionView;
			if (isEdit && session) {
				// media_type is immutable on edit — never send it. The update schema
				// has no media_type field, so omit it rather than rely on the backend
				// silently dropping an extra key.
				result = await updateSession(session.id, {
					name,
					rip_preset_id: ripId,
					transcode_preset_id: tcId || null,
					output_path_template: template,
					overrides_json: parsedOverrides,
				});
			} else {
				result = await createSession({
					name,
					media_type: mediaType,
					rip_preset_id: ripId,
					transcode_preset_id: tcId || null,
					output_path_template: template,
					overrides_json: parsedOverrides,
				});
			}
			onsaved(result);
		} catch (err) {
			submitError = err instanceof Error ? err.message : 'Failed to save session';
		} finally {
			submitting = false;
		}
	}
</script>

<div
	role="dialog"
	aria-modal="true"
	aria-label={isEdit ? 'Edit session' : 'Create session'}
	class="flex flex-col gap-5"
>
	<form onsubmit={handleSubmit} class="flex flex-col gap-5">
		{#if readOnly}
			<div
				class="rounded-md border border-amber-300 bg-amber-50 px-3 py-2 text-sm text-amber-800 dark:border-amber-700/50 dark:bg-amber-900/20 dark:text-amber-300"
				data-testid="sb-builtin-note"
				role="status"
			>
				This is a built-in session and can't be edited. Clone it to make an editable copy.
			</div>
		{/if}

		<!-- Session name -->
		<div class="flex flex-col gap-1">
			<label for="sb-name" class="text-sm font-medium text-gray-700 dark:text-gray-300">
				Session name
			</label>
			<input
				id="sb-name"
				type="text"
				class="w-full rounded-md border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary disabled:cursor-not-allowed disabled:opacity-50 dark:border-gray-600 dark:bg-gray-800 dark:text-gray-100"
				bind:value={name}
				placeholder="e.g. Movies — Archive"
				disabled={readOnly}
				required
			/>
		</div>

		<!-- Media type segmented control -->
		<div class="flex flex-col gap-1">
			<span class="text-sm font-medium text-gray-700 dark:text-gray-300">Media type</span>
			<div class="flex flex-wrap gap-1">
				{#each MEDIA_TYPES as mt (mt.value)}
					<button
						type="button"
						onclick={() => switchMediaType(mt.value)}
						disabled={isEdit || readOnly}
						class="rounded-md border px-3 py-1 text-sm font-medium transition-colors
							{mediaType === mt.value
								? 'border-primary bg-primary text-white'
								: 'border-gray-300 bg-white text-gray-600 hover:bg-gray-50 dark:border-gray-600 dark:bg-gray-800 dark:text-gray-300 dark:hover:bg-gray-700'}
							disabled:cursor-not-allowed disabled:opacity-50"
					>
						{mt.label}
					</button>
				{/each}
			</div>
		</div>

		<!-- Rip preset -->
		<div class="flex flex-col gap-1">
			<label for="sb-rip" class="text-sm font-medium text-gray-700 dark:text-gray-300">
				Rip preset
				<span class="ml-1 text-red-500">*</span>
			</label>
			<select
				id="sb-rip"
				class="w-full rounded-md border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary disabled:cursor-not-allowed disabled:opacity-50 dark:border-gray-600 dark:bg-gray-800 dark:text-gray-100"
				value={ripId}
				onchange={handleRipChange}
				disabled={readOnly}
				required
			>
				<option value="">— select a rip preset —</option>
				{#each ripOptions as rp (rp.id)}
					<option value={rp.id}>{rp.name}</option>
				{/each}
				<option value="__create_rip__">+ Create new rip preset…</option>
			</select>
		</div>

		<!-- Transcode preset (optional) -->
		<div class="flex flex-col gap-1">
			<label for="sb-tc" class="text-sm font-medium text-gray-700 dark:text-gray-300">
				Transcode preset
				<span class="ml-1 text-xs text-gray-400">(optional)</span>
			</label>
			<select
				id="sb-tc"
				class="w-full rounded-md border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary disabled:cursor-not-allowed disabled:opacity-50 dark:border-gray-600 dark:bg-gray-800 dark:text-gray-100"
				value={tcId}
				onchange={handleTcChange}
				disabled={readOnly}
			>
				<option value="">No transcode — rip only</option>
				{#each tcOptions as tc (tc.id)}
					<option value={tc.id}>{tc.name}</option>
				{/each}
				<option value="__create_tc__">+ Create new transcode preset…</option>
			</select>
		</div>

		<!-- Output path template -->
		<div class="flex flex-col gap-1">
			<label for="sb-path" class="text-sm font-medium text-gray-700 dark:text-gray-300">
				Output path
				<span class="ml-1 text-red-500">*</span>
			</label>
			<OutputPathField
				id="sb-path"
				value={template}
				mediaType={mediaType}
				onchange={(v) => { template = v; }}
				has_transcode_preset={!!tcId}
				disabled={readOnly}
			/>
		</div>

		<!-- Advanced (collapsed) -->
		<details class="rounded-md border border-gray-200 dark:border-gray-700">
			<summary class="cursor-pointer select-none px-3 py-2 text-sm font-medium text-gray-600 dark:text-gray-400">
				Advanced
			</summary>
			<div class="flex flex-col gap-2 px-3 pb-3 pt-2">
				<label for="sb-overrides" class="text-xs font-medium text-gray-600 dark:text-gray-400">
					Overrides JSON
				</label>
				<textarea
					id="sb-overrides"
					class="w-full rounded-md border border-gray-300 bg-white px-3 py-2 font-mono text-xs text-gray-900 focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary disabled:cursor-not-allowed disabled:opacity-50 dark:border-gray-600 dark:bg-gray-800 dark:text-gray-100"
					rows="4"
					bind:value={overridesJson}
					placeholder={`{"key": "value"}`}
					disabled={readOnly}
				></textarea>
				{#if jsonError}
					<p class="text-xs text-red-600 dark:text-red-400">{jsonError}</p>
				{/if}
			</div>
		</details>

		{#if submitError}
			<p class="text-sm text-red-600 dark:text-red-400">{submitError}</p>
		{/if}

		<!-- Footer -->
		<div class="flex items-center justify-between gap-3 border-t border-gray-200 pt-4 dark:border-gray-700">
			<div class="text-xs text-gray-400 dark:text-gray-500">
				{#if !tcId}
					Rips only — no transcode step.
				{/if}
			</div>
			<div class="flex gap-2">
				<button
					type="button"
					onclick={oncancel}
					class="rounded-md border border-gray-300 px-4 py-2 text-sm font-medium text-gray-600 hover:bg-gray-50 dark:border-gray-600 dark:text-gray-300 dark:hover:bg-gray-800"
				>
					{readOnly ? 'Close' : 'Cancel'}
				</button>
				{#if !readOnly}
					<button
						type="submit"
						disabled={!canSubmit || submitting}
						class="rounded-md bg-primary px-4 py-2 text-sm font-medium text-white hover:bg-primary/90 disabled:cursor-not-allowed disabled:opacity-50"
					>
						{isEdit ? 'Save changes' : 'Create session'}
					</button>
				{/if}
			</div>
		</div>
	</form>
</div>
