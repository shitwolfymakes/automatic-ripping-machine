<script lang="ts">
	import { onMount } from 'svelte';
	import { createSessionsData, type JoinedSession } from '../../stores/sessions-data.svelte';
	import { copyName, isRipPreset, ripPresetCopy, transcodePresetCopy } from '../../sessions/session-presets';
	import SessionsHub from './SessionsHub.svelte';
	import PresetLibrary from './PresetLibrary.svelte';
	import RoutingMatrix from './RoutingMatrix.svelte';
	import SessionBuilderSlideOver from './SessionBuilderSlideOver.svelte';
	import RipPresetSidebar from './RipPresetSidebar.svelte';
	import PresetSidebar from '$lib/components/handbrake/PresetSidebar.svelte';
	import type { SidebarMode } from '$lib/handbrake/display';
	import ConfirmDialog from '$lib/components/shared/ConfirmDialog.svelte';
	import { deleteSession, cloneSession } from '$lib/api/sessions';
	import { createRipPreset, deleteRipPreset } from '$lib/api/rip-presets';
	import { createTranscodePreset, deleteTranscodePreset } from '$lib/api/transcode-presets';
	import { addToast } from '$lib/stores/toast.svelte';
	import { errorMessage } from '$lib/utils/errors';
	import { transcoderEnabled } from '$lib/stores/config';
	import {
		activePresetKey,
		activeSessionKey,
		deletePresetMessage,
		deleteSessionMessage,
		isCreatingRipPreset,
		isCreatingTranscodePreset,
		isRipSidebarReadOnly,
		isSidebarStacked,
		shouldCloseBuilderAfterDelete,
		shouldClosePresetEditorsAfterDelete,
		transcodeSidebarMode,
		viewTabs,
		passthroughSessions,
		passthroughTranscodePresets,
		type EditorState,
		type View
	} from '../../sessions/sessions-area-model';
	import { countByMediaType } from '$lib/sessions/sessions';
	import type { RipPresetView, SessionView, TranscodePresetView } from '$lib/types/api.gen';

	const data = createSessionsData();

	// A ripper-only deployment (not transcode-capable) shows only passthrough
	// sessions/presets. Keyed on capability, not the runtime toggle: a
	// capable-but-disabled box keeps its encode sessions editable.
	const shownSessions = $derived(
		$transcoderEnabled ? data.sessions() : passthroughSessions(data.sessions(), data.transcodePresets())
	);
	const shownTranscodePresets = $derived(
		$transcoderEnabled ? data.transcodePresets() : passthroughTranscodePresets(data.transcodePresets())
	);
	const shownTypeCounts = $derived($transcoderEnabled ? data.typeCounts() : countByMediaType(shownSessions));

	// Active view: the sessions hub, one of the two preset libraries, or routing
	let view = $state<View>('sessions');

	// Each list view's count, shown on its tab; Routing has none.
	const tabs = $derived(
		viewTabs({
			sessions: shownSessions.length,
			rip: data.ripPresets().length,
			transcode: shownTranscodePresets.length
		})
	);

	// Builder slide-over
	let builderOpen = $state(false);
	let editing = $state<JoinedSession | null>(null);

	// Rip presets: the rip preset sidebar, open while set; its preset is the one
	// to view or edit, null to create one.
	let ripSidebar = $state<{ preset: RipPresetView | null } | null>(null);
	// Transcode presets: the preset sidebar, open while set.
	let sidebar = $state<{ preset: TranscodePresetView | null; mode: SidebarMode } | null>(null);
	const editor = $derived<EditorState>({
		builderOpen,
		sessionId: editing?.id ?? null,
		ripPresetId: ripSidebar?.preset?.id ?? null,
		transcodePresetId: sidebar?.preset?.id ?? null
	});
	const activePresetId = $derived(activePresetKey(editor));
	const activeSessionId = $derived(activeSessionKey(editor));
	let preselectRipId = $state<string | undefined>(undefined);
	let preselectTranscodeId = $state<string | undefined>(undefined);

	// Confirm-delete state for sessions and presets
	let deleteSessionTarget = $state<JoinedSession | null>(null);
	let deletePresetTarget = $state<RipPresetView | TranscodePresetView | null>(null);

	onMount(data.load);

	// Runs a change, then reloads. A change that throws skips the reload
	// and toasts `failTitle` with what went wrong. Says whether the change worked.
	async function reloadAfter(change: () => Promise<unknown>, failTitle: string): Promise<boolean> {
		try {
			await change();
			await data.load();
			return true;
		} catch (e) {
			addToast({ tone: 'error', title: failTitle, body: errorMessage(e, 'Unknown error') });
			return false;
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

	// open confirm dialog instead of deleting immediately
	function handleDeleteSession(s: JoinedSession) {
		deleteSessionTarget = s;
	}

	async function confirmDeleteSession() {
		// ConfirmDialog fires onconfirm only while open, which is only while the target is set.
		const target = deleteSessionTarget as JoinedSession;
		deleteSessionTarget = null;
		const deleted = await reloadAfter(() => deleteSession(target.id), 'Delete failed');
		// A failed delete keeps its builder open; a deleted session has nothing left to edit.
		if (shouldCloseBuilderAfterDelete(target.id, deleted, editor)) handleBuilderCancel();
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

	// View/Edit: each kind of preset opens its sidebar (read-only for a built-in). PresetLibrary passes (preset); the
	// kind is inferred from the preset shape.
	function openPresetForm(p: RipPresetView | TranscodePresetView) {
		if (isRipPreset(p)) {
			ripSidebar = { preset: p };
		} else {
			sidebar = { preset: p, mode: transcodeSidebarMode(p) };
		}
	}

	function handleCloneRipPreset(p: RipPresetView): Promise<boolean> {
		return reloadAfter(() => createRipPreset(ripPresetCopy(p)), 'Clone failed');
	}

	// Cloning from the read-only sidebar leaves the original's sidebar once the copy exists.
	async function cloneFromSidebar(p: RipPresetView) {
		if (await handleCloneRipPreset(p)) closeRipSidebar();
	}

	function handleCloneTranscodePreset(p: TranscodePresetView): Promise<boolean> {
		return reloadAfter(() => createTranscodePreset(transcodePresetCopy(p)), 'Clone failed');
	}

	async function cloneTranscodeFromSidebar(p: TranscodePresetView) {
		if (await handleCloneTranscodePreset(p)) closeSidebar();
	}

	async function handleClonePreset(p: RipPresetView | TranscodePresetView) {
		if (isRipPreset(p)) {
			await handleCloneRipPreset(p);
		} else {
			await handleCloneTranscodePreset(p);
		}
	}

	// open confirm before deleting a preset
	function handleDeletePreset(p: RipPresetView | TranscodePresetView) {
		deletePresetTarget = p;
	}

	async function confirmDeletePreset() {
		// ConfirmDialog fires onconfirm only while open, which is only while the target is set.
		const target = deletePresetTarget as RipPresetView | TranscodePresetView;
		deletePresetTarget = null;
		const deleted = await reloadAfter(
			() => (isRipPreset(target) ? deleteRipPreset(target.id) : deleteTranscodePreset(target.id)),
			'Delete failed'
		);
		// A failed delete keeps its editor open; a deleted preset has nothing left to edit.
		if (shouldClosePresetEditorsAfterDelete(target.id, deleted, editor)) {
			closeSidebar();
			closeRipSidebar();
		}
	}

	// ── Preset sidebar callbacks ──────────────────────────────────────────────

	// Opens the sidebar on a new rip preset.
	function openNewRipPreset() {
		ripSidebar = { preset: null };
	}

	// Opens the sidebar on a new transcode preset.
	function openNewTranscodePreset() {
		sidebar = { preset: null, mode: 'new' };
	}

	function closeRipSidebar() {
		ripSidebar = null;
	}

	function closeSidebar() {
		sidebar = null;
	}

	async function handleRipPresetSaved(p: RipPresetView) {
		const wasCreating = isCreatingRipPreset(ripSidebar);
		closeRipSidebar();
		await data.load();
		// Only pre-select when creating a new preset (not when editing an existing one)
		if (wasCreating) {
			preselectRipId = p.id;
		}
	}

	async function handleTranscodePresetSaved(p: TranscodePresetView) {
		const wasCreating = isCreatingTranscodePreset(sidebar);
		closeSidebar();
		await data.load();
		if (wasCreating) {
			preselectTranscodeId = p.id;
		}
	}
</script>

<div class="stack stack-lg">
	<!-- Header -->
	<div class="sessions-area-header">
		<div class="sessions-area-heading">
			<h2 class="sessions-area-title" data-page-section-title>Sessions</h2>
			<p class="sessions-area-lede">
				Sessions bundle a rip preset, an optional transcode preset, and an output-path template into a reusable recipe.
				Choose a session when inserting a disc.
			</p>
			<p class="sessions-area-lede sessions-area-presets-note">
				Presets are reusable building blocks: each preset can be used by multiple sessions, and changing one affects
				every session that references it.
			</p>
		</div>

		<!-- View switch: Sessions / Rip presets / Transcode presets / Routing -->
		<div class="sessions-area-tabs-box">
			<div class="tabs tabs-pills sessions-area-tabs" role="tablist" aria-label="Sessions sections">
				{#each tabs as tab (tab.key)}
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
						{#if tab.count !== undefined}
							<span class="sessions-area-tab-count">{tab.count}</span>
						{/if}
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
			activeKey={activeSessionId}
			onnew={openNewSession}
			onedit={openEditSession}
			onclone={handleCloneSession}
			ondelete={handleDeleteSession}
		/>
	{:else if view === 'routing'}
		<RoutingMatrix />
	{:else}
		<PresetLibrary
			kind={view}
			ripPresets={data.ripPresets()}
			transcodePresets={shownTranscodePresets}
			ripUsage={data.ripUsage}
			transcodeUsage={data.transcodeUsage}
			loading={data.loading()}
			activeKey={activePresetId}
			onnewrip={openNewRipPreset}
			onnewtranscode={openNewTranscodePreset}
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
		oncreaterip={openNewRipPreset}
		oncreatetranscode={openNewTranscodePreset}
		onsaved={handleBuilderSaved}
		oncancel={handleBuilderCancel}
		{preselectRipId}
		{preselectTranscodeId}
	/>
{/if}

<!-- ── Rip preset sidebar ─────────────────────────────────────────────── -->
{#if ripSidebar}
	<RipPresetSidebar
		preset={ripSidebar.preset}
		readOnly={isRipSidebarReadOnly(ripSidebar.preset)}
		stacked={isSidebarStacked(editor)}
		usage={ripSidebar.preset ? data.ripUsage(ripSidebar.preset.id) : 0}
		onclone={cloneFromSidebar}
		onsaved={handleRipPresetSaved}
		onclose={closeRipSidebar}
	/>
{/if}

<!-- ── Transcode preset sidebar ───────────────────────────────────────── -->
{#if sidebar}
	<PresetSidebar
		preset={sidebar.preset}
		mode={sidebar.mode}
		usage={sidebar.preset ? data.transcodeUsage(sidebar.preset.id) : 0}
		onclone={cloneTranscodeFromSidebar}
		onclose={closeSidebar}
		onsaved={handleTranscodePresetSaved}
	/>
{/if}

<!-- ── Confirm: delete session ────────────────────────────────────────────── -->
<ConfirmDialog
	open={deleteSessionTarget !== null}
	title="Delete session"
	message={deleteSessionMessage(deleteSessionTarget)}
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
	message={deletePresetMessage(deletePresetTarget)}
	confirmLabel="Delete"
	variant="danger"
	onconfirm={confirmDeletePreset}
	oncancel={() => {
		deletePresetTarget = null;
	}}
/>

<style>
	/* wrapping row (items-start, justify-between, gap-4); .page-header
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
	/* Takes the room the view switch leaves, so the switch sits top right
	   and only wraps below the text when the window is too narrow for both. */
	.sessions-area-heading {
		flex: 1 1 28rem;
		min-width: 0;
		max-width: 56rem;
	}
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
	.sessions-area-presets-note {
		margin-top: 0.875rem;
	}
	.sessions-area-tab-count {
		margin-left: 0.375rem;
		font-variant-numeric: tabular-nums;
		opacity: 0.7;
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
	/* padding is 0.75rem/0.375rem, not tabs-pills'
	   default 0.25rem 0.75rem - 2px taller per side. */
	/* reach the imported block's class from this scoped selector */
	.sessions-area-tabs :global(.tabs-tab) {
		padding: 0.375rem 0.75rem;
	}
</style>
