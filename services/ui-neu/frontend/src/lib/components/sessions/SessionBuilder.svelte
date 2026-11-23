<script lang="ts">
	import { errorMessage } from '$lib/utils/errors';
	import type {
		MediaType,
		MusicCoverSize,
		MusicTagField,
		SessionView,
		RipPresetView,
		TranscodePresetView
	} from '$lib/types/api.gen';
	import { transcodePresetFits } from '$lib/sessions/sessions';
	import type { JoinedSession } from '../../stores/sessions-data.svelte';
	import { createSession, updateSession } from '$lib/api/sessions';
	import type { EditorStatus } from '$lib/ui/editor-status';
	import OutputPathField from './OutputPathField.svelte';
	import { errorId, focusFirstInvalid, invalidAttrs } from '$lib/ui/form-validation';
	import FieldLabel from '$lib/components/shared/FieldLabel.svelte';
	import CheckListField from '$lib/components/shared/CheckListField.svelte';
	import { ALL_MUSIC_TAGS, COVER_SIZE_OPTIONS, DEFAULT_COVER_SIZE, MUSIC_TAG_OPTIONS } from '$lib/sessions/music-tags';
	import {
		FIELD_IDS,
		SESSION_FIELDS,
		SESSION_FIELD_ORDER,
		parseOverrides,
		sessionErrors,
		sessionUpdate,
		sessionCreate,
		showsCoverSize,
		showsMusicTags,
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
	let musicTags = $state<MusicTagField[]>([...(session?.music_tag_fields ?? ALL_MUSIC_TAGS)]);
	let coverSize = $state<MusicCoverSize>(session?.music_cover_size ?? DEFAULT_COVER_SIZE);
	// The Advanced section opens itself when Save sends focus to the overrides field inside it.
	let advancedOpen = $state(false);
	let submitError = $state<string | null>(null);
	let submitting = $state(false);

	// Derived options filtered by media type
	let ripOptions = $derived(ripPresets.filter((p) => p.media_type === mediaType));
	// A movie or TV transcode preset fits a session of either.
	let tcOptions = $derived(transcodePresets.filter((p) => transcodePresetFits(p.media_type, mediaType)));

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

	// The media chips are disabled on edit and for a built-in session, so this
	// only runs while the media type may still change.
	function switchMediaType(mt: MediaType) {
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

		const form: SessionForm = {
			name,
			mediaType,
			ripId,
			tcId,
			template,
			overrides: parseOverrides(overridesJson),
			musicTags,
			coverSize
		};

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
			<FieldLabel for={SESSION_FIELDS.name} label="Session name" docsId={FIELD_IDS.name} />
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
			<FieldLabel label="Media type" docsId={FIELD_IDS.media_type} />
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
			<FieldLabel for={SESSION_FIELDS.rip} label="Rip preset" docsId={FIELD_IDS.rip_preset} required />
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
		<div class="field">
			<FieldLabel for="sb-tc" label="Transcode preset" docsId={FIELD_IDS.transcode_preset}>
				{#snippet marks()}<span class="session-builder-optional">(optional)</span>{/snippet}
			</FieldLabel>
			<select id="sb-tc" value={tcId} onchange={handleTcChange} disabled={readOnly}>
				<option value="">No transcode, rip only</option>
				{#each tcOptions as tc (tc.id)}
					<option value={tc.id}>{tc.name}</option>
				{/each}
				<option value="__create_tc__">+ Create new transcode preset...</option>
			</select>
		</div>

		<!-- Output path template -->
		<div class="field">
			<FieldLabel for={SESSION_FIELDS.path} label="Output path" docsId={FIELD_IDS.output_path} required />
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

		<!-- Music file tags: a music session that encodes -->
		{#if showsMusicTags(mediaType, tcId)}
			<div class="field" data-testid="sb-music-tags">
				<FieldLabel label="Music file tags" docsId={FIELD_IDS.music_tags} />
				<CheckListField
					options={MUSIC_TAG_OPTIONS}
					bind:value={musicTags}
					legend="Music file tags"
					idPrefix="sb-music-tag"
					helpId="sb-music-tags-help"
					disabled={readOnly}
				/>
				<p class="field-help" id="sb-music-tags-help">
					What this session writes into each track it encodes. An unticked tag is left out of the file.
				</p>
			</div>
		{/if}

		<!-- Cover art size: when the cover is one of the music tags -->
		{#if showsCoverSize(mediaType, tcId, musicTags)}
			<div class="field" data-testid="sb-cover-size">
				<FieldLabel for="sb-cover-size" label="Cover art size" docsId={FIELD_IDS.cover_size} />
				<select id="sb-cover-size" bind:value={coverSize} aria-describedby="sb-cover-size-help" disabled={readOnly}>
					{#each COVER_SIZE_OPTIONS as option (option.value)}
						<option value={option.value}>{option.label}</option>
					{/each}
				</select>
				<p class="field-help" id="sb-cover-size-help">
					The Cover Art Archive image embedded in each track, by its longest side. A cover uploaded smaller than the
					size chosen is embedded as uploaded. A cover URL entered on the job is used as entered.
				</p>
			</div>
		{/if}

		<!-- Advanced (collapsed) -->
		<details class="session-builder-advanced" bind:open={advancedOpen}>
			<summary class="session-builder-advanced-summary"> Advanced </summary>
			<div class="stack stack-sm session-builder-advanced-body">
				<FieldLabel for={SESSION_FIELDS.overrides} label="Overrides JSON" docsId={FIELD_IDS.overrides} />
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
	/* text-red-500 (same shade in both modes). --color-danger is red-600 in light / red-400 in
	   dark, a mode-dependent shift; accepted since no mode-independent danger role exists. */
	/* text-xs text-gray-400 (gray-500 in dark) - text-faint
	   already flips gray-400/gray-500 across modes, matching exactly. */
	.session-builder-optional {
		font-size: 0.75rem;
		line-height: 1rem;
		color: var(--color-text-faint);
	}
	/* media-type chips are rounded-md border px-3 py-1 text-sm
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
	/* a plain neutral-bordered disclosure with no equivalent block. */
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
	/* text-xs font-medium
	   (12px/16px) - field-label's own default is 0.875rem/1.25rem/600, tuned
	   for a top-level field label, not this smaller nested-textarea caption. */
	/* :global: the label is rendered by the child FieldLabel component, outside this component's own template */
	.session-builder-advanced-body :global(.field-label) {
		font-size: 0.75rem;
		line-height: 1rem;
		font-weight: 500;
		color: var(--color-text-secondary);
	}
</style>
