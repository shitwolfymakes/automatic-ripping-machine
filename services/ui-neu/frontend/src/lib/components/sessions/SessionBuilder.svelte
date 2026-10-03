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
	class="stack stack-lg"
>
	<form onsubmit={handleSubmit} class="stack stack-lg">
		{#if readOnly}
			<div
				class="alert alert-warning"
				data-testid="sb-builtin-note"
				role="status"
			>
				This is a built-in session and can't be edited. Clone it to make an editable copy.
			</div>
		{/if}

		<!-- Session name -->
		<label for="sb-name" class="field">
			<span class="field-label">Session name</span>
			<input
				id="sb-name"
				type="text"
				bind:value={name}
				placeholder="e.g. Movies: Archive"
				disabled={readOnly}
				required
			/>
		</label>

		<!-- Media type segmented control -->
		<div class="field">
			<span class="field-label">Media type</span>
			<div class="cluster">
				{#each MEDIA_TYPES as mt (mt.value)}
					<button
						type="button"
						onclick={() => switchMediaType(mt.value)}
						disabled={isEdit || readOnly}
						aria-pressed={mediaType === mt.value}
						class="chip session-builder-media-chip"
					>
						{mt.label}
					</button>
				{/each}
			</div>
		</div>

		<!-- Rip preset -->
		<label for="sb-rip" class="field">
			<span class="field-label">Rip preset <span class="session-builder-required">*</span></span>
			<select
				id="sb-rip"
				value={ripId}
				onchange={handleRipChange}
				disabled={readOnly}
				required
			>
				<option value="">Select a rip preset</option>
				{#each ripOptions as rp (rp.id)}
					<option value={rp.id}>{rp.name}</option>
				{/each}
				<option value="__create_rip__">+ Create new rip preset...</option>
			</select>
		</label>

		<!-- Transcode preset (optional) -->
		<label for="sb-tc" class="field">
			<span class="field-label">Transcode preset <span class="session-builder-optional">(optional)</span></span>
			<select
				id="sb-tc"
				value={tcId}
				onchange={handleTcChange}
				disabled={readOnly}
			>
				<option value="">No transcode, rip only</option>
				{#each tcOptions as tc (tc.id)}
					<option value={tc.id}>{tc.name}</option>
				{/each}
				<option value="__create_tc__">+ Create new transcode preset...</option>
			</select>
		</label>

		<!-- Output path template -->
		<div class="field">
			<label class="field-label" for="sb-path">Output path <span class="session-builder-required">*</span></label>
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
		<details class="session-builder-advanced">
			<summary class="session-builder-advanced-summary">
				Advanced
			</summary>
			<div class="stack stack-sm session-builder-advanced-body">
				<label for="sb-overrides" class="field-label session-builder-overrides-label">
					Overrides JSON
				</label>
				<textarea
					id="sb-overrides"
					class="mono field-control"
					rows="4"
					bind:value={overridesJson}
					placeholder={`{"key": "value"}`}
					disabled={readOnly}
				></textarea>
				{#if jsonError}
					<p class="field-error">{jsonError}</p>
				{/if}
			</div>
		</details>

		{#if submitError}
			<p class="field-error">{submitError}</p>
		{/if}

		<!-- Footer -->
		<div class="session-builder-footer">
			<div class="session-builder-footer-note">
				{#if !tcId}
					Rips only, no transcode step.
				{/if}
			</div>
			<div class="cluster">
				<button
					type="button"
					onclick={oncancel}
					class="btn"
				>
					{readOnly ? 'Close' : 'Cancel'}
				</button>
				{#if !readOnly}
					<button
						type="submit"
						disabled={!canSubmit || submitting}
						class="btn btn-primary session-builder-submit-btn"
					>
						{isEdit ? 'Save changes' : 'Create session'}
					</button>
				{/if}
			</div>
		</div>
	</form>
</div>

<style>
	/* original: ml-1 text-red-500 (no dark: variant - same shade in both modes).
	   --color-danger is red-600 in light / red-400 in dark, a mode-dependent
	   shift the original never had; kept anyway per the migration reference's
	   own ruling (row 38: "red-600 reads fine as both fill and text") since no
	   mode-independent danger role exists in spec 5.1. */
	.session-builder-required { margin-left: 0.25rem; color: var(--color-danger); }
	/* original: ml-1 text-xs text-gray-400 dark:text-gray-500 - text-faint
	   already flips gray-400/gray-500 across modes, matching exactly. */
	.session-builder-optional { margin-left: 0.25rem; font-size: 0.75rem; line-height: 1rem; color: var(--color-text-faint); }
	/* original media-type chips: rounded-md border px-3 py-1 text-sm
	   font-medium - chip's own radius (--radius-sm), padding (0.125rem
	   0.375rem) and size (0.75rem) are tuned for the tighter filter-pill look,
	   so the segmented-control metrics are restated here on top of chip's
	   base cursor/transition/selected-state colours. */
	.session-builder-media-chip { border: 1px solid var(--color-border-strong); border-radius: var(--radius-md); background: var(--color-surface-raised); padding: 0.25rem 0.75rem; font-size: 0.875rem; line-height: 1.25rem; font-weight: 500; color: var(--color-text-secondary); }
	.session-builder-media-chip:hover { background: var(--color-primary-tint-1); }
	.session-builder-media-chip[aria-pressed="true"] { border-color: var(--color-primary); background: var(--color-primary); color: var(--color-on-primary); }
	.session-builder-media-chip:disabled { opacity: 0.5; cursor: not-allowed; }
	/* original: rounded-md border border-gray-200 dark:border-gray-700 - a
	   plain neutral-bordered disclosure with no equivalent block. */
	.session-builder-advanced { border: 1px solid var(--color-border); border-radius: var(--radius-md); }
	.session-builder-advanced-summary { cursor: pointer; user-select: none; padding: 0.5rem 0.75rem; font-size: 0.875rem; line-height: 1.25rem; font-weight: 500; color: var(--color-text-secondary); }
	.session-builder-advanced-body { padding: 0.5rem 0.75rem 0.75rem; }
	/* original: text-xs font-medium text-gray-600 dark:text-gray-400
	   (12px/16px) - field-label's own default is 0.875rem/1.25rem/600, tuned
	   for a top-level field label, not this smaller nested-textarea caption. */
	.session-builder-overrides-label { font-size: 0.75rem; line-height: 1rem; font-weight: 500; color: var(--color-text-secondary); }
	.session-builder-footer { display: flex; align-items: center; justify-content: space-between; gap: 0.75rem; border-top: 1px solid var(--color-border); padding-top: 1rem; }
	.session-builder-footer-note { font-size: 0.75rem; line-height: 1rem; color: var(--color-text-faint); }
	/* original submit button: rounded-md bg-primary ... - no border/ring class
	   at all. .btn-primary's own 1px border is invisible (same colour as the
	   fill) but still occupies 2px of layout height, and its default radius
	   is --radius-lg, not the original's smaller --radius-md (Task 9/10
	   finding: a bare fill button with no border class needs border: 0). */
	.session-builder-submit-btn { border: 0; border-radius: var(--radius-md); }
</style>
