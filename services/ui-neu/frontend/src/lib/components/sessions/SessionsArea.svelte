<script lang="ts">
	import { onMount } from 'svelte';
	import { createSessionsData, type JoinedSession } from './sessionsData.svelte';
	import SessionsHub from './SessionsHub.svelte';
	import PresetLibrary from './PresetLibrary.svelte';
	import SessionBuilder from './SessionBuilder.svelte';
	import RipPresetForm from '$lib/components/RipPresetForm.svelte';
	import TranscodePresetForm from '$lib/components/TranscodePresetForm.svelte';
	import ConfirmDialog from '$lib/components/ConfirmDialog.svelte';
	import CloseButton from '$lib/components/CloseButton.svelte';
	import { deleteSession, cloneSession } from '$lib/api/sessions';
	import {
		createRipPreset,
		deleteRipPreset,
	} from '$lib/api/ripPresets';
	import {
		createTranscodePreset,
		deleteTranscodePreset,
	} from '$lib/api/transcodePresets';
	import { addToast } from '$lib/stores/toast.svelte';
	import type { RipPresetView, SessionView, TranscodePresetView } from '$lib/types/api.gen';

	const data = createSessionsData();

	// Active sub-tab: sessions hub, or one of the two preset libraries
	let view = $state<'sessions' | 'rip' | 'transcode'>('sessions');

	const TABS: Array<{ key: 'sessions' | 'rip' | 'transcode'; label: string }> = [
		{ key: 'sessions', label: 'Sessions' },
		{ key: 'rip', label: 'Rip presets' },
		{ key: 'transcode', label: 'Transcode presets' },
	];

	// Builder slide-over
	let builderOpen = $state(false);
	let editing = $state<JoinedSession | null>(null);

	// Inline-create / inline-edit stacked dialog.
	// When kind is set, the dialog opens. editingPreset carries an existing preset
	// for edit mode; null means create mode.
	let inlineKind = $state<'rip' | 'transcode' | null>(null);
	let inlinePreset = $state<RipPresetView | TranscodePresetView | null>(null);
	let preselectRipId = $state<string | undefined>(undefined);
	let preselectTranscodeId = $state<string | undefined>(undefined);

	// Confirm-delete state for sessions and presets
	let deleteSessionTarget = $state<JoinedSession | null>(null);
	let deletePresetTarget = $state<RipPresetView | TranscodePresetView | null>(null);

	onMount(data.load);

	// ── Sessions view callbacks ────────────────────────────────────────────────

	function openNewSession() {
		editing = null;
		builderOpen = true;
	}

	function openEditSession(s: JoinedSession) {
		editing = s;
		builderOpen = true;
	}

	async function handleCloneSession(s: JoinedSession) {
		try {
			await cloneSession(s.id, { name: `${s.name} (copy)` });
			await data.load();
		} catch (e) {
			addToast({ tone: 'error', title: 'Clone failed', body: e instanceof Error ? e.message : 'Unknown error' });
		}
	}

	// FIX 1: open confirm dialog instead of deleting immediately
	function handleDeleteSession(s: JoinedSession) {
		deleteSessionTarget = s;
	}

	async function confirmDeleteSession() {
		if (!deleteSessionTarget) return;
		const target = deleteSessionTarget;
		deleteSessionTarget = null;
		try {
			await deleteSession(target.id);
			await data.load();
		} catch (e) {
			const msg = e instanceof Error ? e.message : 'Unknown error';
			addToast({ tone: 'error', title: 'Delete failed', body: msg });
		}
	}

	// Applying a session needs a job context (ApplySessionDialog requires a job),
	// so it lives on the job page — the settings hub does not apply sessions.

	// ── Builder callbacks ──────────────────────────────────────────────────────

	function handleBuilderSaved(_s: SessionView) {
		builderOpen = false;
		data.load();
	}

	function handleBuilderCancel() {
		builderOpen = false;
		editing = null;
	}

	// ── Preset library callbacks ───────────────────────────────────────────────

	// FIX 2: wire View/Edit to open the form in the stacked dialog.
	// PresetLibrary passes (preset) — the kind is inferred from the preset shape.
	function openPresetForm(p: RipPresetView | TranscodePresetView) {
		inlineKind = 'track_selection' in p ? 'rip' : 'transcode';
		inlinePreset = p;
	}

	function handleViewPreset(p: RipPresetView | TranscodePresetView) {
		openPresetForm(p);
	}

	function handleEditPreset(p: RipPresetView | TranscodePresetView) {
		openPresetForm(p);
	}

	async function handleCloneRipPreset(p: RipPresetView) {
		try {
			await createRipPreset({
				name: `${p.name} (copy)`,
				media_type: p.media_type,
				track_selection: p.track_selection,
				identification_mode: p.identification_mode,
				output_mode: p.output_mode,
				// track_filters_json is { [key: string]: unknown } | null in the API;
				// RipPresetView carries it as unknown — narrow with a cast.
				track_filters_json: p.track_filters_json as { [key: string]: unknown } | null,
			});
			await data.load();
		} catch (e) {
			addToast({ tone: 'error', title: 'Clone failed', body: e instanceof Error ? e.message : 'Unknown error' });
		}
	}

	async function handleCloneTranscodePreset(p: TranscodePresetView) {
		try {
			await createTranscodePreset({
				name: `${p.name} (copy)`,
				media_type: p.media_type,
				tool: p.tool,
				preset_ref: p.preset_ref ?? null,
				container: p.container,
				// VideoCodec | null — the view's codec is VideoCodec | null, compatible.
				codec: p.codec ?? null,
				hw_preference: p.hw_preference ?? null,
				extra_args: p.extra_args ?? null,
			});
			await data.load();
		} catch (e) {
			addToast({ tone: 'error', title: 'Clone failed', body: e instanceof Error ? e.message : 'Unknown error' });
		}
	}

	async function handleClonePreset(p: RipPresetView | TranscodePresetView) {
		if ('track_selection' in p) {
			await handleCloneRipPreset(p as RipPresetView);
		} else {
			await handleCloneTranscodePreset(p as TranscodePresetView);
		}
	}

	// FIX 1 (preset): open confirm before deleting a preset
	function handleDeletePreset(p: RipPresetView | TranscodePresetView) {
		deletePresetTarget = p;
	}

	async function confirmDeletePreset() {
		if (!deletePresetTarget) return;
		const target = deletePresetTarget;
		deletePresetTarget = null;
		try {
			if ('track_selection' in target) {
				await deleteRipPreset(target.id);
			} else {
				await deleteTranscodePreset(target.id);
			}
			await data.load();
		} catch (e) {
			const msg = e instanceof Error ? e.message : 'Unknown error';
			addToast({ tone: 'error', title: 'Delete failed', body: msg });
		}
	}

	// ── Inline-create / inline-edit callbacks ─────────────────────────────────

	function closeInline() {
		inlineKind = null;
		inlinePreset = null;
	}

	async function handleRipPresetSaved(p: RipPresetView) {
		const wasCreating = inlinePreset === null;
		closeInline();
		await data.load();
		// Only pre-select when creating a new preset (not when editing an existing one)
		if (wasCreating) {
			preselectRipId = p.id;
		}
	}

	async function handleTranscodePresetSaved(p: TranscodePresetView) {
		const wasCreating = inlinePreset === null;
		closeInline();
		await data.load();
		if (wasCreating) {
			preselectTranscodeId = p.id;
		}
	}

	// Inline dialog label for ARIA
	let inlineDialogLabel = $derived(
		inlineKind === 'rip'
			? (inlinePreset ? 'Edit rip preset' : 'New rip preset')
			: (inlinePreset ? 'Edit transcode preset' : 'New transcode preset')
	);
</script>

<div class="stack stack-lg">
	<!-- Header -->
	<div class="sessions-area-header">
		<div>
			<h2 class="sessions-area-title">Sessions</h2>
			<p class="sessions-area-lede">
				Sessions bundle a rip preset, an optional transcode preset, and an output-path template
				into a reusable recipe. Choose a session when inserting a disc.
			</p>
		</div>

		<!-- Sub-tab bar: Sessions / Rip presets / Transcode presets -->
		<div class="sessions-area-tabs-box">
			<div class="tabs tabs-pills sessions-area-tabs" role="tablist" aria-label="Sessions sections">
				{#each TABS as tab}
					<button
						type="button"
						role="tab"
						aria-selected={view === tab.key}
						onclick={() => { view = tab.key; }}
						class="tabs-tab"
					>
						{tab.label}
					</button>
				{/each}
			</div>
		</div>
	</div>

	<!-- Error banner -->
	{#if data.error()}
		<p class="alert alert-danger">
			{data.error()}
		</p>
	{/if}

	<!-- Main content area -->
	{#if view === 'sessions'}
		<SessionsHub
			sessions={data.sessions()}
			typeCounts={data.typeCounts()}
			loading={data.loading()}
			onnew={openNewSession}
			onedit={openEditSession}
			onclone={handleCloneSession}
			ondelete={handleDeleteSession}
		/>
	{:else}
		<PresetLibrary
			kind={view}
			ripPresets={data.ripPresets()}
			transcodePresets={data.transcodePresets()}
			ripUsage={data.ripUsage}
			transcodeUsage={data.transcodeUsage}
			loading={data.loading()}
			onnewrip={() => { inlineKind = 'rip'; inlinePreset = null; }}
			onnewtranscode={() => { inlineKind = 'transcode'; inlinePreset = null; }}
			onview={handleViewPreset}
			onedit={handleEditPreset}
			onclone={handleClonePreset}
			ondelete={handleDeletePreset}
		/>
	{/if}
</div>

<!-- ── Builder slide-over ──────────────────────────────────────────────────── -->
{#if builderOpen}
	<div class="slide-over">
		<!-- Backdrop: a button (not a click handler on the flex container),
			 same pattern as ConfirmDialog.svelte - the panel sits in its own
			 stacking context via z-index so it never needs a stopPropagation
			 click guard, which a11y flags on non-interactive elements. -->
		<button type="button" class="sessions-area-scrim" aria-label="Close panel" onclick={handleBuilderCancel}></button>

		<div class="slide-over-panel sessions-area-slide-over-panel">
			<div class="slide-over-header">
				<h2 class="sessions-area-dialog-title">
					{editing?.is_builtin ? 'View session' : editing ? 'Edit session' : 'Create a session'}
				</h2>
				<CloseButton onclick={handleBuilderCancel} />
			</div>

			<div class="sessions-area-builder-body">
				<SessionBuilder
					session={editing}
					ripPresets={data.ripPresets()}
					transcodePresets={data.transcodePresets()}
					oncreaterip={() => { inlineKind = 'rip'; inlinePreset = null; }}
					oncreatetranscode={() => { inlineKind = 'transcode'; inlinePreset = null; }}
					onsaved={handleBuilderSaved}
					oncancel={handleBuilderCancel}
					preselectRipId={preselectRipId}
					preselectTranscodeId={preselectTranscodeId}
				/>
			</div>
		</div>
	</div>
{/if}

<!-- ── Inline-create / inline-edit stacked dialog ────────────────────── -->
{#if inlineKind !== null}
	<!-- Stacked modal: same shape as .modal, but layered above the builder
		 slide-over (z-index bumped in the scoped rule below - the block's own
		 z-index of 50 would sit under the slide-over's 50 in source order). -->
	<div class="modal sessions-area-inline-modal">
		<button type="button" class="sessions-area-scrim" aria-label="Close dialog" onclick={closeInline}></button>

		<div
			role="dialog"
			aria-modal="true"
			aria-label={inlineDialogLabel}
			class="modal-panel sessions-area-inline-panel"
		>
			{#if inlineKind === 'rip'}
				<RipPresetForm
					preset={inlinePreset as RipPresetView | null}
					onsaved={handleRipPresetSaved}
					oncancel={closeInline}
				/>
			{:else}
				<TranscodePresetForm
					preset={inlinePreset as TranscodePresetView | null}
					onsaved={handleTranscodePresetSaved}
					oncancel={closeInline}
				/>
			{/if}
		</div>
	</div>
{/if}

<!-- ── Confirm: delete session ────────────────────────────────────────────── -->
<ConfirmDialog
	open={deleteSessionTarget !== null}
	title="Delete session"
	message={deleteSessionTarget ? `Delete the session "${deleteSessionTarget.name}"? This cannot be undone.` : ''}
	confirmLabel="Delete"
	variant="danger"
	onconfirm={confirmDeleteSession}
	oncancel={() => { deleteSessionTarget = null; }}
/>

<!-- ── Confirm: delete preset ─────────────────────────────────────────────── -->
<ConfirmDialog
	open={deletePresetTarget !== null}
	title="Delete preset"
	message={deletePresetTarget ? `Delete the preset "${deletePresetTarget.name}"? This cannot be undone.` : ''}
	confirmLabel="Delete"
	variant="danger"
	onconfirm={confirmDeletePreset}
	oncancel={() => { deletePresetTarget = null; }}
/>

<style>
	/* original: flex flex-wrap items-start justify-between gap-4 - .page-header
	   is items-center/gap-3/margin-bottom-6, tuned for a top-level H1 row, not
	   this sub-tab header (items-start, gap-4, no own margin - the stack-lg
	   parent supplies spacing to the next sibling). */
	.sessions-area-header { display: flex; flex-wrap: wrap; align-items: flex-start; justify-content: space-between; gap: 1rem; }
	/* page.css's .page-title is 1.5rem/700 for a top-level H1; this is a
	   sub-tab section H2 (text-lg font-semibold, 1.125rem/1.75rem). */
	.sessions-area-title { font-size: 1.125rem; line-height: 1.75rem; font-weight: 600; color: var(--color-text); }
	.sessions-area-lede { margin-top: 0.25rem; font-size: 0.875rem; line-height: 1.25rem; color: var(--color-text-muted); }
	/* the pills sit in a bordered/shadowed box (rounded-lg border bg-surface
	   p-1 shadow-xs) that tabs-pills itself does not draw - tabs-pills is
	   just the flex row + pill fill. */
	.sessions-area-tabs-box { flex-shrink: 0; border: 1px solid var(--color-border); border-radius: var(--radius-lg); background: var(--color-surface); box-shadow: var(--shadow-1); padding: 0.25rem; }
	/* original padding was px-3 py-1.5 (0.75rem/0.375rem), not tabs-pills'
	   default 0.25rem 0.75rem - 2px taller per side. */
	.sessions-area-tabs :global(.tabs-tab) { padding: 0.375rem 0.75rem; } /* reach the imported block's class from this scoped selector */
	.sessions-area-dialog-title { font-size: 1.125rem; line-height: 1.75rem; font-weight: 600; color: var(--color-text); }
	.sessions-area-builder-body { flex: 1; overflow-y: auto; padding: 1.5rem; }
	/* the inline create/edit dialog stacks above the builder slide-over
	   (both are z-index: 50 in their block files); bump this one layer
	   higher so it wins the stacking contest the original's z-60/z-70
	   pairing guaranteed explicitly. */
	.sessions-area-inline-modal { z-index: 60; }
	/* scrim button covers the backdrop box behind the panel, same pattern as
	   ConfirmDialog.svelte - the panel gets its own stacking context via
	   z-index so no click-guard is needed on the panel itself. */
	.sessions-area-scrim { position: absolute; inset: 0; z-index: 0; background: transparent; border: 0; padding: 0; cursor: default; }
	.sessions-area-slide-over-panel { position: relative; z-index: 1; }
	.sessions-area-inline-panel { position: relative; z-index: 1; }
</style>
