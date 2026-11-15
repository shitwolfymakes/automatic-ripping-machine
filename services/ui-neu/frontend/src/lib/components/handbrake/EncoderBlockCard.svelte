<script lang="ts">
	// One per-encoder settings card on the Video tab: the title with its hardware
	// status, then the family's bit depth and block fields that `fields` names, which
	// show the encoder's defaults as inherited. A stored bit depth shows a Changed mark,
	// one no variant offers stays selectable as an extra option, and its issue marks the select. A card for a device the host cannot verify stays
	// collapsed until the user chooses to set values anyway.
	import type { HandbrakeSchemaSlimView, SettingIssue, SlimFamily, SlimKey } from '$lib/types/api.gen';
	import {
		BIT_DEPTH_FIELD,
		blockDefault,
		blockFields,
		cardKey,
		cardStatusLine,
		cardVariant,
		depthOptions,
		depthText,
		VARIANT_LISTS,
		type EncoderCard
	} from '$lib/handbrake/encoder-cards';
	import { docsHref, familyDocs } from '$lib/docs/field-docs';
	import { errorId, invalidAttrs } from '$lib/ui/form-validation';
	import type { BaseValues } from '$lib/handbrake/base-values';
	import TunableField from './TunableField.svelte';

	interface Props {
		schema: HandbrakeSchemaSlimView;
		family: SlimFamily;
		card: EncoderCard;
		block: Record<string, unknown>;
		base: BaseValues;
		// False while the card shows only its title and the Set values anyway button.
		open: boolean;
		// The inputs the card shows: bit depth and block key names.
		fields: string[];
		inheritedDepth: number;
		depthSource: 'block' | 'base' | 'default';
		issues: SettingIssue[];
		readonly: boolean;
		onchange: (key: string, value: unknown) => void;
		onreset: (key: string) => void;
		onexpand: () => void;
	}

	let {
		schema,
		family,
		card,
		block,
		base,
		open,
		fields,
		inheritedDepth,
		depthSource,
		issues,
		readonly,
		onchange,
		onreset,
		onexpand
	}: Props = $props();

	const prefix = $derived(`${family.name}-`);
	const depthId = $derived(`${family.name}-bit-depth`);
	const variant = $derived(cardVariant(family, block, inheritedDepth));
	const defaultDepthLabel = $derived(
		depthSource === 'base' ? `${depthText(inheritedDepth)}, from base preset` : `${depthText(inheritedDepth)}, default`
	);
	const status = $derived(cardStatusLine(card));
	const depthStored = $derived(block.bit_depth !== undefined);
	const depthChoices = $derived(depthOptions(family, block));
	const depthIssue = $derived(issueFor(BIT_DEPTH_FIELD.name));

	// Resolved eagerly: TunableField only reads the props its kind needs, which would leave these branches lazy.
	const rows = $derived(
		blockFields(schema, family)
			.filter((key) => fields.includes(key.name))
			.map((key) => ({
				name: key.name,
				shown: cardKey(key, variant),
				options: options(key),
				inherited: blockDefault(key, variant, base),
				range: rangeFor(key),
				issue: issueFor(key.name)
			}))
	);

	function options(key: SlimKey): string[] | null {
		const list = VARIANT_LISTS[key.name];
		if (!list) return null;
		return variant[list] as string[];
	}

	function rangeFor(key: SlimKey) {
		if (key.name !== 'VideoQualitySlider') return undefined;
		const q = variant.quality;
		return { min: q.low, max: q.high, step: q.step };
	}

	function issueFor(name: string): SettingIssue | undefined {
		return issues.find((i) => i.encoder === family.name && i.key === name);
	}

	function onDepth(e: Event) {
		const raw = (e.currentTarget as HTMLSelectElement).value;
		const chosen = family.variants.find((v) => depthText(v.depth) === raw);
		if (chosen) onchange(BIT_DEPTH_FIELD.name, chosen.depth);
		else onreset(BIT_DEPTH_FIELD.name);
	}
</script>

<section class="form-card encoder-card" data-state={card.state} aria-label={card.label}>
	{#if !open}
		<div class="encoder-card-collapsed">
			<div class="encoder-card-summary">
				<h4 class="encoder-card-title">{card.label}</h4>
				<p class="encoder-card-status">{status}</p>
			</div>
			<button type="button" class="btn-link encoder-card-anyway" onclick={onexpand}>Set values anyway</button>
		</div>
	{:else}
		<div class="form-card-head encoder-card-head">
			<h4 class="encoder-card-title">{card.label}</h4>
			{#if status}<span class="encoder-card-badge" data-state={card.state}>{status}</span>{/if}
		</div>
		<div class="encoder-card-fields">
			{#if fields.includes(BIT_DEPTH_FIELD.name)}
				<div class="tunable-field" data-stored={depthStored}>
					<div class="tunable-field-head">
						<span class="tunable-field-inline">
							<label class="field-label" for={depthId}>Bit depth</label>
							{#if depthStored}<span class="changed-chip">Changed</span>{/if}
						</span>
						{#if depthStored}
							<button type="button" class="btn-link" disabled={readonly} onclick={() => onreset(BIT_DEPTH_FIELD.name)}
								>Reset</button
							>
						{/if}
					</div>
					<select
						id={depthId}
						class="field-control"
						disabled={readonly}
						onchange={onDepth}
						{...invalidAttrs(depthId, depthIssue?.message)}
					>
						<option value="" selected={!depthStored}>{defaultDepthLabel}</option>
						{#each depthChoices as choice (choice.text)}
							<option selected={choice.selected}>{choice.text}</option>
						{/each}
					</select>
					{#if depthIssue}<p class="field-error" id={errorId(depthId)} role="alert">{depthIssue.message}</p>{/if}
				</div>
			{/if}
			{#each rows as row (row.name)}
				<TunableField
					key={row.shown}
					value={block[row.name]}
					inherited={row.inherited}
					stored={block[row.name] !== undefined}
					options={row.options}
					issue={row.issue}
					disabled={readonly}
					idPrefix={prefix}
					range={row.range}
					docUrl={docsHref(familyDocs(family.name))}
					onchange={(v) => onchange(row.name, v)}
					onreset={() => onreset(row.name)}
				/>
			{/each}
		</div>
	{/if}
</section>

<style>
	.encoder-card {
		display: flex;
		flex-direction: column;
		gap: 0.75rem;
	}
	.encoder-card-head,
	.encoder-card-collapsed {
		display: flex;
		align-items: center;
		gap: 0.5rem;
	}
	.encoder-card-collapsed {
		justify-content: space-between;
		gap: 0.75rem;
	}
	.encoder-card-title {
		margin: 0;
		flex: 1;
		font-size: 0.8125rem;
		font-weight: 700;
		color: var(--color-text);
	}
	.encoder-card-summary {
		flex: 1;
	}
	.encoder-card-status {
		margin: 0.125rem 0 0;
		font-size: 0.8125rem;
		color: var(--color-text-secondary);
	}
	.encoder-card-anyway {
		font-size: 0.75rem;
	}
	.encoder-card-badge {
		padding: 0.125rem 0.4375rem;
		border-radius: 999px;
		font-size: 0.625rem;
		font-weight: 700;
		background: var(--color-info-soft);
		color: var(--color-on-info-soft);
	}
	.encoder-card-badge[data-state='verified'] {
		background: var(--color-success-soft);
		color: var(--color-on-success-soft);
	}
	.encoder-card-badge[data-state='cpu-fallback'] {
		background: var(--color-warning-soft);
		color: var(--color-on-warning-soft);
	}
	.encoder-card-fields {
		display: grid;
		grid-template-columns: repeat(2, minmax(0, 1fr));
		gap: 0.625rem;
	}
	.tunable-field {
		display: flex;
		flex-direction: column;
		gap: 0.25rem;
		min-width: 0;
	}
	.tunable-field-head {
		display: flex;
		align-items: baseline;
		justify-content: space-between;
		gap: 0.5rem;
	}
	.tunable-field-inline {
		display: flex;
		align-items: center;
		gap: 0.5rem;
	}
</style>
