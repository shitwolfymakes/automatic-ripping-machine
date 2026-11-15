<script lang="ts">
	// One per-encoder settings card on the Video tab: the title with its hardware
	// status, then the family's bit depth and block fields that `fields` names, which
	// show the encoder's defaults as inherited. A card for a device the host cannot verify stays
	// collapsed until the user chooses to set values anyway.
	import type { HandbrakeSchemaSlimView, SettingIssue, SlimFamily, SlimKey } from '$lib/types/api.gen';
	import {
		blockDefault,
		blockFields,
		cardStatusLine,
		VARIANT_LISTS,
		type EncoderCard
	} from '$lib/handbrake/encoderCards';
	import type { BaseValues } from '$lib/handbrake/sidebarModel';
	import TunableField from './TunableField.svelte';

	interface Props {
		schema: HandbrakeSchemaSlimView;
		family: SlimFamily;
		card: EncoderCard;
		block: Record<string, unknown>;
		base: BaseValues;
		// False while the card shows only its title and the Set values anyway button.
		open: boolean;
		// The inputs the card shows: 'bit_depth' and block key names.
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
	const depth = $derived(typeof block.bit_depth === 'number' ? block.bit_depth : inheritedDepth);
	const variant = $derived(family.variants.find((v) => v.depth === depth) ?? family.variants[0]);
	const depthText = (d: number) => `${d}-bit`;
	const defaultDepthLabel = $derived(
		depthSource === 'base' ? `${depthText(inheritedDepth)}, from base preset` : `${depthText(inheritedDepth)}, default`
	);
	const status = $derived(cardStatusLine(card));

	// Resolved eagerly: TunableField only reads the props its kind needs, which would leave these branches lazy.
	const rows = $derived(
		blockFields(schema, family)
			.filter((key) => fields.includes(key.name))
			.map((key) => ({
				name: key.name,
				shown: shownKey(key),
				options: options(key),
				inherited: blockDefault(key, variant, base),
				range: rangeFor(key),
				issue: issueFor(key)
			}))
	);

	function options(key: SlimKey): string[] | null {
		const list = VARIANT_LISTS[key.name];
		if (!list) return null;
		return variant[list] as string[];
	}

	// The variant supplies these lists, so the key renders as a select though the schema names no source.
	function shownKey(key: SlimKey): SlimKey {
		if (key.name in VARIANT_LISTS) return { ...key, source: { kind: 'variant', ref: key.name } };
		if (key.name === 'VideoOptionExtra') return { ...key, label: 'Extra encoder options' };
		if (key.name !== 'VideoQualitySlider') return key;
		const q = variant.quality;
		return { ...key, label: `Quality (${q.name}, ${q.low} to ${q.high})` };
	}

	function rangeFor(key: SlimKey) {
		if (key.name !== 'VideoQualitySlider') return undefined;
		const q = variant.quality;
		return { min: q.low, max: q.high, step: q.step };
	}

	function issueFor(key: SlimKey): SettingIssue | undefined {
		return issues.find((i) => i.encoder === family.name && i.key === key.name);
	}

	function onDepth(e: Event) {
		const raw = (e.currentTarget as HTMLSelectElement).value;
		const chosen = family.variants.find((v) => depthText(v.depth) === raw);
		if (chosen) onchange('bit_depth', chosen.depth);
		else onreset('bit_depth');
	}
</script>

<section class="encoder-card" data-state={card.state} aria-label={card.label}>
	{#if !open}
		<div class="encoder-card-collapsed">
			<div class="encoder-card-summary">
				<h4 class="encoder-card-title">{card.label}</h4>
				<p class="encoder-card-status">{status}</p>
			</div>
			<button type="button" class="btn-link encoder-card-anyway" onclick={onexpand}>Set values anyway</button>
		</div>
	{:else}
		<header class="encoder-card-head">
			<h4 class="encoder-card-title">{card.label}</h4>
			{#if status}<span class="encoder-card-badge" data-state={card.state}>{status}</span>{/if}
		</header>
		<div class="encoder-card-fields">
			{#if fields.includes('bit_depth')}
				<div class="tunable-field" data-stored={block.bit_depth !== undefined}>
					<div class="tunable-field-head">
						<label class="field-label" for={depthId}>Bit depth</label>
						{#if block.bit_depth !== undefined}
							<button type="button" class="btn-link" disabled={readonly} onclick={() => onreset('bit_depth')}
								>Reset</button
							>
						{/if}
					</div>
					<select id={depthId} class="field-control" disabled={readonly} onchange={onDepth}>
						<option value="" selected={block.bit_depth === undefined}>{defaultDepthLabel}</option>
						{#each family.variants as v (v.depth)}
							<option selected={block.bit_depth === v.depth}>{depthText(v.depth)}</option>
						{/each}
					</select>
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
		padding: 0.875rem;
		border: 1px solid var(--color-border);
		border-radius: var(--radius-md);
		background: var(--color-primary-tint-1);
	}
	.encoder-card[data-state='verified'] {
		border-color: var(--color-border-strong);
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
</style>
