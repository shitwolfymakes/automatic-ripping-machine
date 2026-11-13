<script lang="ts">
	import { errorMessage } from '$lib/utils/errors';
	import type { MediaType, SessionView, RipPresetView, TranscodePresetView } from '$lib/types/api.gen';
	import type { JoinedSession } from '../../sessions/sessions-data.svelte';
	import { createSession, updateSession } from '$lib/api/sessions';
	import type { EditorStatus } from '$lib/components/editor-status';
	import OutputPathField from './OutputPathField.svelte';
	import { errorId, focusFirstInvalid, invalidAttrs } from '$lib/utils/formValidation';
	import {
		SESSION_FIELDS,
		SESSION_FIELD_ORDER,
		parseOverrides,
		sessionErrors,
		sessionUpdate,
		sessionCreate,
		type SessionForm
	} from '../../sessions/session-form';

	interface Props {
		session?: JoinedSession | null;
		ripPresets: RipPresetView[];
		transcodePresets: TranscodePresetView[];
		oncreaterip: () => void;
		oncreatetranscode: () => void;
		onsaved: (s: SessionView) => void;
		preselectRipId?: string;
		preselectTranscodeId?: string;
		/** The hosting EditorSidebar's footer owns the buttons and submits this form by id. */
		formId: string;
		/** Reports the save state to the hosting footer, whenever it changes. */
		onstatus?: (status: EditorStatus) => void;
	}

	let {
		session,
		ripPresets,
		transcodePresets,
		oncreaterip,
		oncreatetranscode,
		onsaved,
		preselectRipId,
		preselectTranscodeId,
		formId,
		onstatus
	}: Props = $props();

	const MEDIA_TYPES: { value: MediaType; label: string }[] = [
		{ value: 'movie', label: 'Movie' },
		{ value: 'tv', label: 'TV' },
		{ value: 'music', label: 'Music' },
		{ value: 'data', label: 'Data' },
		{ value: 'iso', label: 'ISO' }
	];

	// Form state
	let name = $state(session?.name ?? '');
	let mediaType = $state<MediaType>(session?.media_type ?? 'movie');
	let ripId = $state(session?.rip_preset_id ?? '');
	let tcId = $state(session?.transcode_preset_id ?? '');
	let template = $state(session?.output_path_template ?? '');
	let overridesJson = $state(session?.overrides_json ? JSON.stringify(session.overrides_json, null, 2) : '');
	// The Advanced section opens itself when Save sends focus to the overrides field inside it.
	let advancedOpen = $state(false);
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
	// Marks show from the first Save on, and each clears once its field is valid.
	let attempted = $state(false);
	const inputs = $derived({ name, ripId, template, overridesText: overridesJson });
	const errors = $derived(attempted ? sessionErrors(inputs) : {});

	$effect(() => {
		onstatus?.({ submitting, note: tcId ? '' : 'Rips only, no transcode step.' });
	});

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
		attempted = true;
		const found = sessionErrors(inputs);
		if (SESSION_FIELDS.overrides in found) advancedOpen = true;
		if (await focusFirstInvalid(found, SESSION_FIELD_ORDER)) return;
		submitError = null;

		const form: SessionForm = { name, mediaType, ripId, tcId, template, overrides: parseOverrides(overridesJson) };

		submitting = true;
		try {
			const result = session
				? await updateSession(session.id, sessionUpdate(form))
				: await createSession(sessionCreate(form));
			onsaved(result);
		} catch (err) {
			submitError = errorMessage(err, 'Failed to save session');
		} finally {
			submitting = false;
		}
	}
</script>

<div class="stack stack-lg">
	<form id={formId} onsubmit={handleSubmit} class="stack stack-lg">
		{#if readOnly}
			<div class="alert alert-warning" data-testid="sb-builtin-note" role="status">
				This is a built-in session and can't be edited. Clone it to make an editable copy.
			</div>
		{/if}

		<!-- Session name -->
		<div class="field">
			<label for={SESSION_FIELDS.name} class="field-label">Session name</label>
			<input
				id={SESSION_FIELDS.name}
				type="text"
				bind:value={name}
				placeholder="e.g. Movies: Archive"
				disabled={readOnly}
				{...invalidAttrs(SESSION_FIELDS.name, errors[SESSION_FIELDS.name])}
			/>
			{@render fieldError(SESSION_FIELDS.name)}
		</div>

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
		<div class="field">
			<label for={SESSION_FIELDS.rip} class="field-label"
				>Rip preset <span class="session-builder-required">*</span></label
			>
			<select
				id={SESSION_FIELDS.rip}
				value={ripId}
				onchange={handleRipChange}
				disabled={readOnly}
				{...invalidAttrs(SESSION_FIELDS.rip, errors[SESSION_FIELDS.rip])}
			>
				<option value="">Select a rip preset</option>
				{#each ripOptions as rp (rp.id)}
					<option value={rp.id}>{rp.name}</option>
				{/each}
				<option value="__create_rip__">+ Create new rip preset...</option>
			</select>
			{@render fieldError(SESSION_FIELDS.rip)}
		</div>

		<!-- Transcode preset (optional) -->
		<label for="sb-tc" class="field">
			<span class="field-label">Transcode preset <span class="session-builder-optional">(optional)</span></span>
			<select id="sb-tc" value={tcId} onchange={handleTcChange} disabled={readOnly}>
				<option value="">No transcode, rip only</option>
				{#each tcOptions as tc (tc.id)}
					<option value={tc.id}>{tc.name}</option>
				{/each}
				<option value="__create_tc__">+ Create new transcode preset...</option>
			</select>
		</label>

		<!-- Output path template -->
		<div class="field">
			<label class="field-label" for={SESSION_FIELDS.path}
				>Output path <span class="session-builder-required">*</span></label
			>
			<OutputPathField
				id={SESSION_FIELDS.path}
				errorId={errors[SESSION_FIELDS.path] ? errorId(SESSION_FIELDS.path) : undefined}
				value={template}
				{mediaType}
				onchange={(v) => {
					template = v;
				}}
				has_transcode_preset={!!tcId}
				disabled={readOnly}
			/>
			{@render fieldError(SESSION_FIELDS.path)}
		</div>

		<!-- Advanced (collapsed) -->
		<details class="session-builder-advanced" bind:open={advancedOpen}>
			<summary class="session-builder-advanced-summary"> Advanced </summary>
			<div class="stack stack-sm session-builder-advanced-body">
				<label for={SESSION_FIELDS.overrides} class="field-label session-builder-overrides-label">
					Overrides JSON
				</label>
				<textarea
					id={SESSION_FIELDS.overrides}
					class="mono field-control"
					rows="4"
					bind:value={overridesJson}
					placeholder={`{"key": "value"}`}
					disabled={readOnly}
					{...invalidAttrs(SESSION_FIELDS.overrides, errors[SESSION_FIELDS.overrides])}></textarea>
				{@render fieldError(SESSION_FIELDS.overrides)}
			</div>
		</details>

		{#if submitError}
			<p class="field-error">{submitError}</p>
		{/if}
	</form>
</div>

{#snippet fieldError(id: string)}
	{#if errors[id]}<p class="field-error" id={errorId(id)}>{errors[id]}</p>{/if}
{/snippet}

<style>
	/* original: ml-1 text-red-500 (no dark: variant - same shade in both modes).
	   --color-danger is red-600 in light / red-400 in dark, a mode-dependent
	   shift the original never had; kept anyway per the migration reference's
	   own ruling (row 38: "red-600 reads fine as both fill and text") since no
	   mode-independent danger role exists in spec 5.1. */
	.session-builder-required {
		margin-left: 0.25rem;
		color: var(--color-danger);
	}
	/* original: ml-1 text-xs text-gray-400 dark:text-gray-500 - text-faint
	   already flips gray-400/gray-500 across modes, matching exactly. */
	.session-builder-optional {
		margin-left: 0.25rem;
		font-size: 0.75rem;
		line-height: 1rem;
		color: var(--color-text-faint);
	}
	/* original media-type chips: rounded-md border px-3 py-1 text-sm
	   font-medium - chip's own radius (--radius-sm), padding (0.125rem
	   0.375rem) and size (0.75rem) are tuned for the tighter filter-pill look,
	   so the segmented-control metrics are restated here on top of chip's
	   base cursor/transition/selected-state colours. */
	.session-builder-media-chip {
		border: 1px solid var(--color-border-strong);
		border-radius: var(--radius-md);
		background: var(--color-surface-raised);
		padding: 0.25rem 0.75rem;
		font-size: 0.875rem;
		line-height: 1.25rem;
		font-weight: 500;
		color: var(--color-text-secondary);
	}
	.session-builder-media-chip:hover {
		background: var(--color-primary-tint-1);
	}
	.session-builder-media-chip[aria-pressed='true'] {
		border-color: var(--color-primary);
		background: var(--color-primary);
		color: var(--color-on-primary);
	}
	.session-builder-media-chip:disabled {
		opacity: 0.5;
		cursor: not-allowed;
	}
	/* original: rounded-md border border-gray-200 dark:border-gray-700 - a
	   plain neutral-bordered disclosure with no equivalent block. */
	.session-builder-advanced {
		border: 1px solid var(--color-border);
		border-radius: var(--radius-md);
	}
	.session-builder-advanced-summary {
		cursor: pointer;
		user-select: none;
		padding: 0.5rem 0.75rem;
		font-size: 0.875rem;
		line-height: 1.25rem;
		font-weight: 500;
		color: var(--color-text-secondary);
	}
	.session-builder-advanced-body {
		padding: 0.5rem 0.75rem 0.75rem;
	}
	/* original: text-xs font-medium text-gray-600 dark:text-gray-400
	   (12px/16px) - field-label's own default is 0.875rem/1.25rem/600, tuned
	   for a top-level field label, not this smaller nested-textarea caption. */
	.session-builder-overrides-label {
		font-size: 0.75rem;
		line-height: 1rem;
		font-weight: 500;
		color: var(--color-text-secondary);
	}
</style>
