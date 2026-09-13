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

<div class="flex flex-col gap-6">
	<!-- Header -->
	<div class="flex flex-wrap items-start justify-between gap-4">
		<div>
			<h2 class="text-lg font-semibold text-gray-900 dark:text-white">Sessions</h2>
			<p class="mt-1 text-sm text-gray-500 dark:text-gray-400">
				Sessions bundle a rip preset, an optional transcode preset, and an output-path template
				into a reusable recipe. Choose a session when inserting a disc.
			</p>
		</div>

		<!-- Sub-tab bar: Sessions / Rip presets / Transcode presets -->
		<div class="flex shrink-0 gap-1 rounded-lg border border-primary/20 bg-surface p-1 shadow-xs dark:bg-surface-dark" role="tablist" aria-label="Sessions sections">
			{#each TABS as tab}
				<button
					type="button"
					role="tab"
					aria-selected={view === tab.key}
					onclick={() => { view = tab.key; }}
					class="rounded-md px-3 py-1.5 text-sm font-medium transition-colors
						{view === tab.key
							? 'bg-primary text-white'
							: 'text-gray-600 hover:bg-gray-100 dark:text-gray-300 dark:hover:bg-gray-700'}"
				>
					{tab.label}
				</button>
			{/each}
		</div>
	</div>

	<!-- Error banner -->
	{#if data.error()}
		<p class="rounded-md bg-red-50 px-4 py-2 text-sm text-red-700 dark:bg-red-900/20 dark:text-red-400">
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
	<!-- Backdrop -->
	<div
		role="presentation"
		class="fixed inset-0 z-40 bg-black/40"
		onclick={handleBuilderCancel}
	></div>

	<!-- Panel -->
	<div
		class="fixed inset-y-0 right-0 z-50 flex w-full max-w-lg flex-col overflow-y-auto bg-white shadow-xl dark:bg-gray-900"
	>
		<div class="flex items-center justify-between border-b border-gray-200 px-6 py-4 dark:border-gray-700">
			<h2 class="text-lg font-semibold text-gray-900 dark:text-white">
				{editing?.is_builtin ? 'View session' : editing ? 'Edit session' : 'Create a session'}
			</h2>
			<CloseButton onclick={handleBuilderCancel} />
		</div>

		<div class="flex-1 overflow-y-auto p-6">
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
{/if}

<!-- ── Inline-create / inline-edit stacked dialog ────────────────────── -->
{#if inlineKind !== null}
	<!-- Stacked backdrop (higher z than the builder) -->
	<div
		role="presentation"
		class="fixed inset-0 z-60 bg-black/50"
		onclick={closeInline}
	></div>

	<!-- Dialog -->
	<div
		role="dialog"
		aria-modal="true"
		aria-label={inlineDialogLabel}
		class="fixed left-1/2 top-1/2 z-70 w-full max-w-md -translate-x-1/2 -translate-y-1/2 overflow-y-auto rounded-lg bg-white p-6 shadow-2xl dark:bg-gray-900"
		style="max-height: 90vh;"
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
