<script lang="ts">
	// The transcode preset sidebar on Settings > Sessions: the preset block,
	// the schema-driven HandBrake settings below it, and one Save that writes
	// both. Built-in presets open read-only.
	import { onMount } from 'svelte';
	import EditorSidebar from '$lib/components/EditorSidebar.svelte';
	import EditorFormFooter from '$lib/components/EditorFormFooter.svelte';
	import LoadState from '$lib/components/LoadState.svelte';
	import PresetBlock from './PresetBlock.svelte';
	import SettingsPanel from './SettingsPanel.svelte';
	import ImportPanel from './ImportPanel.svelte';
	import { fetchBuiltinPreset } from '$lib/api/handbrakeSchema';
	import { createTranscodePreset, updateTranscodePreset } from '$lib/api/transcodePresets';
	import { handbrakeSchema } from '$lib/stores/handbrakeSchema.svelte';
	import { encodersStore } from '$lib/stores/encoders.svelte';
	import { presetSidebarView } from '$lib/handbrake/panelView';
	import {
		VAAPI_NOTE,
		applyField,
		draftToCreate,
		draftToUpdate,
		footerNote,
		initialDraft,
		onBaseChange,
		saveFailure,
		schemaLoadError,
		panelCards,
		showTabs,
		sidebarTitle,
		usageLabel,
		type Bases,
		type PresetField,
		type SaveFailure,
		type SidebarMode
	} from '$lib/handbrake/sidebarModel';
	import { applyProposal } from '$lib/handbrake/importReview';
	import { unplacedIssues, unplacedText } from '$lib/handbrake/issuePlacement';
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

	let open = $state(true);
	let draft = $state(initialDraft(preset));
	let issues = $state<SettingIssue[]>(preset?.issues ?? []);
	let bases = $state<Bases>({});
	let submitting = $state(false);
	let failure = $state<SaveFailure | null>(null);
	let importing = $state(false);
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

	async function save(event: SubmitEvent) {
		event.preventDefault();
		if (!view.canSubmit) return;
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
	}
</script>

{#snippet footer()}
	{#if note}<p class="preset-sidebar-note">{note}</p>{/if}
	<EditorFormFooter
		note={usageLabel(usage)}
		readOnly={readonly}
		formId={FORM_ID}
		canSubmit={view.canSubmit}
		{submitting}
		{onclose}
	/>
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
		<button type="button" class="btn btn-sm" disabled={view.importDisabled} onclick={() => (importing = true)}
			>Import HandBrake preset</button
		>
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
				<ul class="alert alert-warning preset-sidebar-issues">
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
