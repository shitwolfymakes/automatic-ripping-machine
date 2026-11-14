<script lang="ts">
	// The transcode preset sidebar on Settings > Sessions: the preset block,
	// the schema-driven HandBrake settings below it, and one Save that writes
	// both. Built-in presets open read-only. A Save with a blank name, or one the
	// backend refuses with per-setting issues, clears the settings filter, opens the
	// tab of the first marked field in form order and focuses it; when no input shows
	// an issue, focus goes to the banner that lists them.
	import { onMount, tick } from 'svelte';
	import EditorSidebar from '$lib/components/shared/EditorSidebar.svelte';
	import EditorFormFooter from '$lib/components/shared/EditorFormFooter.svelte';
	import LoadState from '$lib/components/shared/LoadState.svelte';
	import PresetBlock from './PresetBlock.svelte';
	import SettingsPanel from './SettingsPanel.svelte';
	import ImportPanel from './ImportPanel.svelte';
	import { fetchBuiltinPreset } from '$lib/api/handbrake-schema';
	import { createTranscodePreset, updateTranscodePreset } from '$lib/api/transcode-presets';
	import { handbrakeSchema } from '$lib/stores/handbrake-schema.svelte';
	import { encodersStore } from '$lib/stores/encoders.svelte';
	import { PRESET_NAME_ID, presetErrors, presetSidebarView } from '$lib/handbrake/panel-view';
	import type { TabId } from '$lib/handbrake/fields';
	import { focusField, focusFirstInvalid } from '$lib/utils/formValidation';
	import {
		VAAPI_NOTE,
		footerNote,
		schemaLoadError,
		sidebarTitle,
		usageLabel,
		type SidebarMode
	} from '$lib/handbrake/display';
	import { applyField, onBaseChange, type Bases } from '$lib/handbrake/draft-rules';
	import { draftToCreate, draftToUpdate, initialDraft, showTabs, type PresetField } from '$lib/handbrake/draft';
	import { panelCards, type FilterState } from '$lib/handbrake/visibility';
	import { saveFailure, type SaveFailure } from '$lib/api/save-failure';
	import { applyProposal } from '$lib/handbrake/import-review';
	import { firstIssueTarget, unplacedIssues, unplacedText, type IssueTarget } from '$lib/handbrake/issuePlacement';
	import type {
		HandbrakeSchemaSlimView,
		ImportedPresetView,
		SettingIssue,
		TranscodePresetView
	} from '$lib/types/api.gen';

	interface Props {
		preset: TranscodePresetView | null;
		mode: SidebarMode;
		usage: number;
		/** Makes an editable copy; offered on a read-only preset. */
		onclone?: (p: TranscodePresetView) => void;
		onclose: () => void;
		onsaved: (p: TranscodePresetView) => void;
	}

	let { preset, mode, usage, onclone, onclose, onsaved }: Props = $props();

	const FORM_ID = 'transcode-preset-sidebar-form';
	const ISSUES_ID = 'transcode-preset-sidebar-issues';

	let open = $state(true);
	let draft = $state(initialDraft(preset));
	let issues = $state<SettingIssue[]>(preset?.issues ?? []);
	let bases = $state<Bases>({});
	let submitting = $state(false);
	let failure = $state<SaveFailure | null>(null);
	let importing = $state(false);
	let tab = $state<TabId>('summary');
	let filter = $state<FilterState>({ text: '', changedOnly: false });
	// The name mark shows from the first Save on, and clears once the name is filled in.
	let attempted = $state(false);
	// The families whose collapsed encoder card the user chose to set values on anyway.
	let expanded = $state<string[]>([]);
	// Built-in names already asked for, so each is fetched once.
	let requested: string[] = [];

	const schema = $derived(handbrakeSchema.schema);
	const base = $derived(bases[draft.preset_ref ?? ''] ?? null);
	const cards = $derived(schema ? panelCards(schema, draft.encoder, draft.preset_ref, encodersStore.list, base) : []);
	// Issues on inputs the panel does not render go to the banner; with no panel, all of them.
	const panel = $derived(
		schema && showTabs(draft) ? { schema, settings: draft.settings, base, cards, expanded } : null
	);
	const loose = $derived(unplacedIssues(issues, panel));
	const errors = $derived(attempted ? presetErrors(draft) : {});
	const cloneAction = $derived(preset && onclone ? () => onclone(preset) : null);
	const view = $derived(
		presetSidebarView({
			mode,
			importing,
			draft,
			submitting,
			cloneAvailable: cloneAction !== null,
			failure,
			unplacedCount: loose.length
		})
	);
	const readonly = $derived(view.readonly);
	const note = $derived(footerNote(preset));

	onMount(() => {
		if (handbrakeSchema.state === 'idle') handbrakeSchema.load();
		loadBase();
	});

	// A failed fetch leaves the fields inheriting HandBrake's defaults.
	async function loadBase() {
		const name = draft.preset_ref;
		if (draft.tool !== 'handbrake' || !name || requested.includes(name)) return;
		requested = [...requested, name];
		try {
			const values = await fetchBuiltinPreset(name);
			bases = { ...bases, [name]: values };
		} catch {
			requested = requested.filter((n) => n !== name);
		}
	}

	async function onfield(field: PresetField, value: string) {
		draft = applyField(draft, field, value, schema, bases);
		await loadBase();
		// A base fetched just now can only be resolved once it has loaded.
		if (field === 'preset_ref') draft = onBaseChange(draft, draft.preset_ref, schema, bases);
	}

	function useImported(imported: ImportedPresetView) {
		draft = applyProposal(draft, imported);
		importing = false;
		loadBase();
	}

	function savePreset(): Promise<TranscodePresetView> {
		if (preset && mode === 'edit') return updateTranscodePreset(preset.id, draftToUpdate(draft));
		return createTranscodePreset(draftToCreate(draft));
	}

	// Clears the filter, so the target's input renders whatever was typed or ticked, and opens its tab.
	function revealTarget(target: IssueTarget) {
		filter = { text: '', changedOnly: false };
		if (target.tab) tab = target.tab;
	}

	// Focuses the first issue's input in form order; with none placed, the banner listing them.
	async function focusFirstIssue(list: SettingIssue[]) {
		const target = firstIssueTarget(list, panel);
		if (target) revealTarget(target);
		await tick();
		focusField(target?.id ?? ISSUES_ID);
	}

	async function save(event: SubmitEvent) {
		event.preventDefault();
		if (!view.canSave) return;
		attempted = true;
		if (await focusFirstInvalid(presetErrors(draft), [PRESET_NAME_ID])) return;
		submitting = true;
		failure = null;
		try {
			onsaved(await savePreset());
		} catch (e) {
			failure = saveFailure(e);
			issues = failure.issues ?? issues;
		} finally {
			submitting = false;
		}
		if (failure?.issues) await focusFirstIssue(failure.issues);
	}
</script>

{#snippet footer()}
	{#if note}<p class="preset-sidebar-note">{note}</p>{/if}
	<EditorFormFooter note={usageLabel(usage)} readOnly={readonly} formId={FORM_ID} {submitting} {onclose} />
{/snippet}

<EditorSidebar
	bind:open
	title={sidebarTitle(mode)}
	width="wide"
	stacked
	footer={view.showFooter ? footer : undefined}
	{onclose}
>
	{#snippet headerActions()}
		{#if view.showClone}
			<button type="button" class="btn btn-sm" onclick={cloneAction}>Clone</button>
		{/if}
		{#if view.showImportButton}
			<button type="button" class="btn btn-sm" disabled={view.importDisabled} onclick={() => (importing = true)}
				>Import HandBrake preset</button
			>
		{/if}
	{/snippet}

	{#if view.showImport}
		<ImportPanel {schema} availability={encodersStore.list} oncancel={() => (importing = false)} onuse={useImported} />
	{:else}
		<form id={FORM_ID} class="preset-sidebar" onsubmit={save}>
			{#if view.failure}
				<div class="alert alert-danger preset-sidebar-banner" role="alert">
					<span>{view.failure.message}</span>
					{#if view.showRetry}
						<button type="button" class="btn btn-sm" onclick={() => handbrakeSchema.retry()}>Retry</button>
					{/if}
				</div>
			{/if}
			{#if view.showUnplaced}
				<ul
					id={ISSUES_ID}
					class="alert alert-warning preset-sidebar-issues"
					tabindex="-1"
					aria-label="Settings issues not shown below"
				>
					{#each loose as issue, i (i)}<li>{unplacedText(issue, schema)}</li>{/each}
				</ul>
			{/if}
			{#if readonly}
				<div class="alert alert-warning" role="status">
					This is a built-in preset and can't be edited. Clone it to make an editable copy.
				</div>
			{/if}

			<PresetBlock
				{draft}
				{readonly}
				editing={mode !== 'new'}
				builtinNames={schema?.builtin_names ?? null}
				{issues}
				{errors}
				{onfield}
			/>

			{#if view.settings === 'tabs'}
				<div class="preset-sidebar-settings">
					<LoadState
						data={schema}
						loading={handbrakeSchema.state === 'loading'}
						error={schemaLoadError(handbrakeSchema.state, handbrakeSchema.error)}
					>
						{#snippet loadingSlot()}<p class="field-help">Loading HandBrake settings...</p>{/snippet}
						{#snippet errorSlot(err: Error)}
							<div class="preset-sidebar-banner">
								<p class="field-error">{err.message}</p>
								<button type="button" class="btn btn-sm" onclick={() => handbrakeSchema.retry()}>Retry</button>
							</div>
						{/snippet}
						{#snippet ready(s: HandbrakeSchemaSlimView)}
							<SettingsPanel
								schema={s}
								settings={draft.settings}
								{base}
								{issues}
								{readonly}
								encoder={draft.encoder}
								availability={encodersStore.list}
								{cards}
								{expanded}
								onsettings={(next) => (draft = { ...draft, settings: next })}
								onexpand={(family) => (expanded = [...expanded, family])}
								bind:tab
								bind:filter
							/>
						{/snippet}
					</LoadState>
				</div>
			{:else if view.settings === 'vaapi-note'}
				<p class="field-help">{VAAPI_NOTE}</p>
			{/if}
		</form>
	{/if}
</EditorSidebar>

<style>
	.preset-sidebar {
		display: flex;
		flex-direction: column;
		gap: 1rem;
	}
	.preset-sidebar-banner {
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: 0.75rem;
	}
	.preset-sidebar-issues {
		margin: 0;
		padding-left: 1.5rem;
		list-style: disc;
	}
	.preset-sidebar-settings {
		padding-top: 0.75rem;
		border-top: 1px solid var(--color-border);
	}
	.preset-sidebar-note {
		font-size: 0.875rem;
		color: var(--color-text-secondary);
	}
</style>
