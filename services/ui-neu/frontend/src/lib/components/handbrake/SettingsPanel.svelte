<script lang="ts">
	// The preset sidebar's HandBrake settings: the tab strip and each tab's
	// schema-rendered fields. The Video tab holds the common keys under "All
	// encoders", then one card per reachable encoder family. Only the inputs the
	// filter and the other settings leave visible render, and a section heading
	// only when something under it does.
	import type {
		EncoderAvailabilityView,
		HandbrakeSchemaSlimView,
		HandbrakeSettings,
		SettingIssue
	} from '$lib/types/api.gen';
	import { fieldOptions, groupsForTab, type TabId } from '$lib/handbrake/fields';
	import { ALL_ENCODERS_LINE, perEncoderLine } from '$lib/handbrake/encoderCards';
	import { visibleTab, type TabVisible, type VisibleInput } from '$lib/handbrake/filter';
	import { changedCount, changedLabel } from '$lib/handbrake/groupSummary';
	import { settingsPanelView } from '$lib/handbrake/panelView';
	import { resetBlock, resetCommon, setBlock, setCommon } from '$lib/handbrake/settingsEdit';
	import {
		AMD_NOTE,
		audioListValue,
		blockOf,
		commonOf,
		inheritedDepth,
		inheritedValue,
		issuesFor,
		panelContext,
		type BaseValues,
		type FilterState
	} from '$lib/handbrake/sidebarModel';
	import SettingsTabs from './SettingsTabs.svelte';
	import TunableField from './TunableField.svelte';
	import EncoderBlockCard from './EncoderBlockCard.svelte';
	import AudioTrackList from './AudioTrackList.svelte';

	interface Props {
		schema: HandbrakeSchemaSlimView;
		settings: HandbrakeSettings;
		base: BaseValues;
		issues: SettingIssue[];
		readonly: boolean;
		encoder: string;
		availability: EncoderAvailabilityView[];
		// The encoder cards the Video tab renders, and the collapsed ones the user expanded.
		cards: VisibleInput['cards'];
		expanded: string[];
		onsettings: (s: HandbrakeSettings) => void;
		onexpand: (family: string) => void;
		/** The open tab; bound by the sidebar, which opens the tab of a field it focuses. */
		tab?: TabId;
		/** The filter text and Changed only; bound by the sidebar, which clears them before it focuses a field. */
		filter: FilterState;
	}

	let {
		schema,
		settings,
		base,
		issues,
		readonly,
		encoder,
		availability,
		cards,
		expanded,
		onsettings,
		onexpand,
		tab = $bindable('summary'),
		filter = $bindable()
	}: Props = $props();

	const common = $derived(commonOf(settings));
	// Selects whose options hang off another key (a filter's presets) read the value in effect.
	const context = $derived(panelContext(schema, settings, base));
	const view = $derived(settingsPanelView({ tab, encoder, availability }));

	const idPrefix = $props.id();
	const headingId = (group: string) => `${idPrefix}-group-${group.toLowerCase().replace(/[^a-z0-9]+/g, '-')}`;
</script>

<SettingsTabs {schema} {settings} {base} {cards} {expanded} {issues} {tab} ontab={(t) => (tab = t)} bind:filter>
	{#snippet children(f: FilterState)}
		{@const shown = visibleTab({ schema, settings, base, filter: f, cards, expanded }, tab)}
		{#if view.section === 'video'}
			{#if shown.rows.length > 0}
				<div class="settings-panel-section">
					<h4 class="settings-panel-heading">All encoders</h4>
					<p class="settings-panel-line">{ALL_ENCODERS_LINE}</p>
				</div>
			{/if}
			{@render fields(shown)}
			{#if shown.cards.length > 0}
				<div class="settings-panel-section settings-panel-divided">
					<h4 class="settings-panel-heading">Per encoder</h4>
					<p class="settings-panel-line">{perEncoderLine(view.encoderLabel)}</p>
				</div>
				{#if view.showAmdNote}<p class="field-help">{AMD_NOTE}</p>{/if}
				<div class="settings-panel-cards">
					{#each shown.cards as { card, family, fields: visible, open } (card.family)}
						{@const depth = inheritedDepth(family, base)}
						<EncoderBlockCard
							{schema}
							{family}
							{card}
							block={blockOf(settings, family.name)}
							{base}
							{open}
							fields={visible}
							inheritedDepth={depth.depth}
							depthSource={depth.source}
							{issues}
							{readonly}
							onchange={(k, v) => onsettings(setBlock(settings, family.name, k, v))}
							onreset={(k) => onsettings(resetBlock(settings, family.name, k))}
							onexpand={() => onexpand(family.name)}
						/>
					{/each}
				</div>
			{/if}
		{:else}
			{@render fields(shown)}
		{/if}
	{/snippet}
</SettingsTabs>

{#snippet fields(shown: TabVisible)}
	{#each groupsForTab(shown.rows.map((r) => r.key)) as { group, keys } (group)}
		{@const changed = changedLabel(changedCount(keys, (name) => name in common))}
		<div class="form-card settings-panel-group" role="group" aria-labelledby={headingId(group)}>
			<div class="form-card-head">
				<h5 class="settings-panel-group-heading" id={headingId(group)}>{group}</h5>
				{#if changed}<span class="changed-chip">{changed}</span>{/if}
			</div>
			<div class="settings-panel-grid">
				{#each shown.rows.filter((r) => keys.includes(r.key)) as { key, row } (key.name)}
					{#if row === 'audio-list'}
						<div class="settings-panel-wide">
							<AudioTrackList
								value={audioListValue(key, settings, base)}
								visibleKeys={shown.tracks}
								{schema}
								{issues}
								{readonly}
								onchange={(v) => onsettings(setCommon(settings, key.name, v))}
							/>
						</div>
					{:else}
						<TunableField
							{key}
							value={common[key.name]}
							inherited={inheritedValue(key, base)}
							stored={key.name in common}
							options={fieldOptions(key, schema, context)}
							issue={issuesFor(issues, key.name)}
							disabled={readonly}
							onchange={(v) => onsettings(setCommon(settings, key.name, v))}
							onreset={() => onsettings(resetCommon(settings, key.name))}
						/>
					{/if}
				{/each}
			</div>
		</div>
	{/each}
{/snippet}

<style>
	.settings-panel-section {
		margin-top: 0.75rem;
	}
	.settings-panel-divided {
		padding-top: 1rem;
		border-top: 1px solid var(--color-border);
	}
	.settings-panel-heading {
		margin: 0;
		font-size: 0.625rem;
		font-weight: 700;
		letter-spacing: 0.08em;
		text-transform: uppercase;
		color: var(--color-text-secondary);
	}
	.settings-panel-line {
		margin: 0.1875rem 0 0.5rem;
		font-size: 0.8125rem;
		line-height: 1.45;
		color: var(--color-text-secondary);
	}
	.settings-panel-group {
		margin-top: 0.75rem;
	}
	.settings-panel-group-heading {
		margin: 0;
		font-size: 0.6875rem;
		font-weight: 600;
		color: var(--color-text-secondary);
	}
	.settings-panel-grid {
		display: grid;
		grid-template-columns: minmax(0, 1fr);
		gap: 0.75rem 1rem;
		margin-top: 0.625rem;
	}
	@media (min-width: 640px) {
		.settings-panel-grid {
			grid-template-columns: repeat(2, minmax(0, 1fr));
		}
	}
	.settings-panel-wide {
		grid-column: 1 / -1;
	}
	.settings-panel-cards {
		display: flex;
		flex-direction: column;
		gap: 0.75rem;
	}
</style>
