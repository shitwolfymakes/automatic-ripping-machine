<script lang="ts">
	import { onMount } from 'svelte';
	import { createSessionsData, type JoinedSession } from './sessionsData.svelte';
	import { copyName, isRipPreset, ripPresetCopy, transcodePresetCopy } from './sessionPresets';
	import SessionsHub from './SessionsHub.svelte';
	import PresetLibrary from './PresetLibrary.svelte';
	import SessionBuilderSlideOver from './SessionBuilderSlideOver.svelte';
	import InlinePresetDialog from './InlinePresetDialog.svelte';
	import ConfirmDialog from '$lib/components/ConfirmDialog.svelte';
	import { deleteSession, cloneSession } from '$lib/api/sessions';
	import { createRipPreset, deleteRipPreset } from '$lib/api/ripPresets';
	import { createTranscodePreset, deleteTranscodePreset } from '$lib/api/transcodePresets';
	import { addToast } from '$lib/stores/toast.svelte';
	import { transcoderEnabled } from '$lib/stores/config';
	import { countByMediaType, isPassthroughSession, presetToolMap, PASSTHROUGH_TOOL } from '$lib/utils/sessions';
	import type { RipPresetView, SessionView, TranscodePresetView } from '$lib/types/api.gen';

	const data = createSessionsData();

	// A ripper-only deployment (not transcode-capable) can never run encode
	// work, so the hub, the builder's transcode picker and the transcode preset
	// library show only passthrough sessions/presets (neu-style hide). Keyed on
	// capability, not the runtime toggle: a capable-but-disabled box keeps its
	// encode sessions editable for when transcoding is switched back on.
	const shownSessions = $derived(
		$transcoderEnabled
			? data.sessions()
			: data.sessions().filter((s) => isPassthroughSession(s, presetToolMap(data.transcodePresets())))
	);
	const shownTranscodePresets = $derived(
		$transcoderEnabled ? data.transcodePresets() : data.transcodePresets().filter((p) => p.tool === PASSTHROUGH_TOOL)
	);
	const shownTypeCounts = $derived($transcoderEnabled ? data.typeCounts() : countByMediaType(shownSessions));

	// Active sub-tab: sessions hub, or one of the two preset libraries
	let view = $state<'sessions' | 'rip' | 'transcode'>('sessions');

	const TABS: Array<{ key: 'sessions' | 'rip' | 'transcode'; label: string }> = [
		{ key: 'sessions', label: 'Sessions' },
		{ key: 'rip', label: 'Rip presets' },
		{ key: 'transcode', label: 'Transcode presets' }
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

	// Runs a change, then reloads. A change that throws skips the reload
	// and toasts `failTitle` with what went wrong.
	async function reloadAfter(change: () => Promise<unknown>, failTitle: string) {
		try {
			await change();
			await data.load();
		} catch (e) {
			addToast({ tone: 'error', title: failTitle, body: e instanceof Error ? e.message : 'Unknown error' });
		}
	}

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
		await reloadAfter(() => cloneSession(s.id, { name: copyName(s.name) }), 'Clone failed');
	}

	// FIX 1: open confirm dialog instead of deleting immediately
	function handleDeleteSession(s: JoinedSession) {
		deleteSessionTarget = s;
	}

	async function confirmDeleteSession() {
		if (!deleteSessionTarget) return;
		const target = deleteSessionTarget;
		deleteSessionTarget = null;
		await reloadAfter(() => deleteSession(target.id), 'Delete failed');
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
		inlineKind = isRipPreset(p) ? 'rip' : 'transcode';
		inlinePreset = p;
	}

	async function handleCloneRipPreset(p: RipPresetView) {
		await reloadAfter(() => createRipPreset(ripPresetCopy(p)), 'Clone failed');
	}

	async function handleCloneTranscodePreset(p: TranscodePresetView) {
		await reloadAfter(() => createTranscodePreset(transcodePresetCopy(p)), 'Clone failed');
	}

	async function handleClonePreset(p: RipPresetView | TranscodePresetView) {
		if (isRipPreset(p)) {
			await handleCloneRipPreset(p);
		} else {
			await handleCloneTranscodePreset(p);
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
		await reloadAfter(
			() => (isRipPreset(target) ? deleteRipPreset(target.id) : deleteTranscodePreset(target.id)),
			'Delete failed'
		);
	}

	// ── Inline-create / inline-edit callbacks ─────────────────────────────────

	// Opens the inline dialog on an empty form of that kind.
	function openNewPreset(kind: 'rip' | 'transcode') {
		inlineKind = kind;
		inlinePreset = null;
	}

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
</script>

<div class="stack stack-lg">
	<!-- Header -->
	<div class="sessions-area-header">
		<div>
			<h2 class="sessions-area-title" data-page-section-title>Sessions</h2>
			<p class="sessions-area-lede">
				Sessions bundle a rip preset, an optional transcode preset, and an output-path template into a reusable recipe.
				Choose a session when inserting a disc.
			</p>
		</div>

		<!-- Sub-tab bar: Sessions / Rip presets / Transcode presets -->
		<div class="sessions-area-tabs-box">
			<div class="tabs tabs-pills sessions-area-tabs" role="tablist" aria-label="Sessions sections">
				{#each TABS as tab (tab.key)}
					<button
						type="button"
						role="tab"
						aria-selected={view === tab.key}
						onclick={() => {
							view = tab.key;
						}}
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
			sessions={shownSessions}
			typeCounts={shownTypeCounts}
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
			transcodePresets={shownTranscodePresets}
			ripUsage={data.ripUsage}
			transcodeUsage={data.transcodeUsage}
			loading={data.loading()}
			onnewrip={() => openNewPreset('rip')}
			onnewtranscode={() => openNewPreset('transcode')}
			onview={openPresetForm}
			onedit={openPresetForm}
			onclone={handleClonePreset}
			ondelete={handleDeletePreset}
		/>
	{/if}
</div>

<!-- ── Builder slide-over ──────────────────────────────────────────────────── -->
{#if builderOpen}
	<SessionBuilderSlideOver
		session={editing}
		ripPresets={data.ripPresets()}
		transcodePresets={shownTranscodePresets}
		oncreaterip={() => openNewPreset('rip')}
		oncreatetranscode={() => openNewPreset('transcode')}
		onsaved={handleBuilderSaved}
		oncancel={handleBuilderCancel}
		{preselectRipId}
		{preselectTranscodeId}
	/>
{/if}

<!-- ── Inline-create / inline-edit stacked dialog ────────────────────── -->
{#if inlineKind !== null}
	<InlinePresetDialog
		kind={inlineKind}
		preset={inlinePreset}
		onripsaved={handleRipPresetSaved}
		ontranscodesaved={handleTranscodePresetSaved}
		onclose={closeInline}
	/>
{/if}

<!-- ── Confirm: delete session ────────────────────────────────────────────── -->
<ConfirmDialog
	open={deleteSessionTarget !== null}
	title="Delete session"
	message={deleteSessionTarget ? `Delete the session "${deleteSessionTarget.name}"? This cannot be undone.` : ''}
	confirmLabel="Delete"
	variant="danger"
	onconfirm={confirmDeleteSession}
	oncancel={() => {
		deleteSessionTarget = null;
	}}
/>

<!-- ── Confirm: delete preset ─────────────────────────────────────────────── -->
<ConfirmDialog
	open={deletePresetTarget !== null}
	title="Delete preset"
	message={deletePresetTarget ? `Delete the preset "${deletePresetTarget.name}"? This cannot be undone.` : ''}
	confirmLabel="Delete"
	variant="danger"
	onconfirm={confirmDeletePreset}
	oncancel={() => {
		deletePresetTarget = null;
	}}
/>

<style>
	/* original: flex flex-wrap items-start justify-between gap-4 - .page-header
	   is items-center/gap-3/margin-bottom-6, tuned for a top-level H1 row, not
	   this sub-tab header (items-start, gap-4, no own margin - the stack-lg
	   parent supplies spacing to the next sibling). */
	.sessions-area-header {
		display: flex;
		flex-wrap: wrap;
		align-items: flex-start;
		justify-content: space-between;
		gap: 1rem;
	}
	/* page.css's .page-title is 1.5rem/700 for a top-level H1; this is a
	   sub-tab section H2 (text-lg font-semibold, 1.125rem/1.75rem). */
	.sessions-area-title {
		font-size: 1.125rem;
		line-height: 1.75rem;
		font-weight: 600;
		color: var(--color-text);
	}
	.sessions-area-lede {
		margin-top: 0.25rem;
		font-size: 0.875rem;
		line-height: 1.25rem;
		color: var(--color-text-muted);
	}
	/* the pills sit in a bordered/shadowed box (rounded-lg border bg-surface
	   p-1 shadow-xs) that tabs-pills itself does not draw - tabs-pills is
	   just the flex row + pill fill. */
	.sessions-area-tabs-box {
		flex-shrink: 0;
		border: 1px solid var(--color-border);
		border-radius: var(--radius-lg);
		background: var(--color-surface);
		box-shadow: var(--shadow-1);
		padding: 0.25rem;
	}
	/* original padding was px-3 py-1.5 (0.75rem/0.375rem), not tabs-pills'
	   default 0.25rem 0.75rem - 2px taller per side. */
	/* reach the imported block's class from this scoped selector */
	.sessions-area-tabs :global(.tabs-tab) {
		padding: 0.375rem 0.75rem;
	}
</style>
