<script lang="ts">
	import type { ConfigFieldMeta } from '$lib/types/api.gen';
	import {
		DISC_KIND_LABELS,
		HINT_LABELS,
		hintIgnored,
		withHintIgnored,
		type DiscHint,
		type DiscKind
	} from '$lib/utils/identity-card';
	import ConfigSchemaField from './ConfigSchemaField.svelte';
	import RankedListField from './RankedListField.svelte';
	import IdentityPreview from './IdentityPreview.svelte';

	// Settings › Identification › Identity: the four pipeline steps over the
	// form's own `values` (bound), so Save, change detection and guest gating
	// stay in SchemaConfigForm. The disc-kind control is view state only.
	let {
		values = $bindable(),
		fields,
		config,
		keyTab,
		disabled = false
	}: {
		values: Record<string, unknown>;
		fields: ConfigFieldMeta[];
		config: Record<string, unknown>;
		keyTab?: (key: string) => string | undefined;
		disabled?: boolean;
	} = $props();

	let kind = $state<DiscKind>('bluray');
	const KINDS: DiscKind[] = ['bluray', 'dvd', 'cd'];

	const meta = (key: string) => fields.find((f) => f.key === key);
	const off = (key: string) => disabled || !meta(key)?.editable;
	// `config` is the saved config; the ranked lists flag a missing key from it
	// merged under the live values (a key typed on another tab is not here).
	const keyConfig = $derived({ ...config, ...values });

	const DISC_DB = [
		{
			key: 'thediscdb_enabled',
			label: 'TheDiscDB disc map',
			chips: ['Blu-ray', 'UHD', 'DVD'],
			description:
				"Matches the disc itself and names its titles before any online lookup. When it matches, it wins over the disc's labels, and ARM confirms the title with the first online source below."
		},
		{ key: 'crc64service_enabled', label: 'ARM community database (CRC64)', chips: ['DVD'], description: null }
	];
	const LISTS = [
		{ key: 'movie_sources', heading: 'Movies' },
		{ key: 'episode_sources', heading: 'TV shows' },
		{ key: 'music_sources', heading: 'Music' }
	];
	const TRUST = [
		{ key: 'movie_auto_apply', label: 'Apply confident matches · Movies' },
		{ key: 'episode_auto_apply', label: 'Apply confident matches · TV shows' },
		{ key: 'music_auto_apply', label: 'Apply confident matches · Music' }
	];
	const IGNORE: { hint: DiscHint; label: string; help: string }[] = [
		{
			hint: 'bd_title',
			label: 'Ignore the disc title metadata',
			help: "Blu-ray and UHD only. ARM won't use the title stored on the disc and identifies it from the volume label, TheDiscDB and online lookup instead."
		},
		{
			hint: 'label',
			label: 'Ignore the volume label',
			help: "ARM won't use the volume label and identifies the disc from its title metadata, TheDiscDB and online lookup instead. A DVD with no title metadata then gets no automatic title search."
		}
	];

	const hasHints = $derived(meta('disc_hint_sources') !== undefined);
	const isIgnored = (hint: DiscHint) => hasHints && hintIgnored(values, hint);
	const isEmpty = (key: string) => Array.isArray(values[key]) && (values[key] as unknown[]).length === 0;
</script>

{#snippet heading(n: number, title: string)}
	<h4 class="identity-card-heading" aria-label="{n} {title}">
		<span class="identity-card-badge" aria-hidden="true">{n}</span>{title}
	</h4>
{/snippet}

{#snippet hintRow(hint: DiscHint, chips: string[])}
	<div class="identity-card-row" data-testid="identity-row-{hint}">
		<div class="identity-card-row-head">
			<span class="identity-card-row-name">{HINT_LABELS[hint]}</span>
			{#each chips as chip (chip)}<span class="chip chip-sm">{chip}</span>{/each}
		</div>
		{#if isIgnored(hint)}
			<p class="identity-card-row-note">Ignored (see Advanced)</p>
		{/if}
	</div>
{/snippet}

<div class="identity-card stack stack-lg" data-testid="identity-card">
	<div class="identity-card-step stack" data-step="preview">
		<span class="label-caps">Preview</span>
		<div class="identity-card-segment" role="radiogroup" aria-label="Disc kind">
			{#each KINDS as k (k)}
				<button
					type="button"
					role="radio"
					aria-checked={kind === k}
					class="identity-card-segment-btn"
					onclick={() => (kind = k)}>{DISC_KIND_LABELS[k]}</button
				>
			{/each}
		</div>
		<IdentityPreview {kind} {values} {fields} />
	</div>

	<div class="identity-card-step stack" data-step="1">
		{@render heading(1, 'On the disc')}
		<div class="identity-card-rows">
			{@render hintRow('bd_title', ['Blu-ray', 'UHD'])}
			{@render hintRow('label', ['All discs'])}
			<div class="identity-card-row" data-testid="identity-row-disc_id">
				<div class="identity-card-row-head">
					<span class="identity-card-row-name">Disc ID (track layout)</span>
					<span class="chip chip-sm">CD</span>
				</div>
			</div>
			<div class="identity-card-row identity-card-planned" data-testid="identity-row-cd_text" aria-disabled="true">
				<div class="identity-card-row-head">
					<span class="identity-card-row-name">CD-TEXT</span>
					<span class="chip chip-sm">CD</span>
					<span class="chip chip-sm">Planned</span>
				</div>
				<p class="identity-card-row-note">Album, artist and track names. Not built yet.</p>
			</div>
		</div>
		<p class="identity-card-note">
			ARM reads all of these. When they disagree, the disc's own metadata beats its label.
		</p>
	</div>

	<div class="identity-card-step stack" data-step="2">
		{@render heading(2, 'Disc database')}
		{#each DISC_DB as db (db.key)}
			{@const field = meta(db.key)}
			{#if field}
				<div class="identity-card-option" id="setting-{db.key}" data-testid="setting-{db.key}">
					<div class="identity-card-row-head">
						<label class="field field-row">
							<input
								type="checkbox"
								aria-label={db.label}
								aria-describedby="identity-help-{db.key}"
								checked={Boolean(values[db.key])}
								disabled={off(db.key)}
								onchange={(e) => (values[db.key] = (e.currentTarget as HTMLInputElement).checked)}
							/>
							<span class="field-label">{db.label}</span>
						</label>
						{#each db.chips as chip (chip)}<span class="chip chip-sm">{chip}</span>{/each}
					</div>
					<p class="field-help" id="identity-help-{db.key}">{db.description ?? field.help}</p>
				</div>
			{/if}
		{/each}
	</div>

	<div class="identity-card-step stack" data-step="3">
		{@render heading(3, 'Online lookup')}
		<p class="identity-card-note" id="identity-help-lookup">Tried top to bottom; the first confident match wins.</p>
		<div class="identity-card-columns">
			{#each LISTS as list (list.key)}
				{@const field = meta(list.key)}
				{#if field}
					<div class="stack identity-card-column" id="setting-{list.key}" data-testid="setting-{list.key}">
						<h5 class="field-label">{list.heading}</h5>
						{#if isEmpty(list.key)}
							<p class="identity-card-note">No sources on</p>
						{/if}
						<RankedListField
							{field}
							bind:value={values[list.key]}
							config={keyConfig}
							helpId="identity-help-lookup"
							{keyTab}
							disabled={off(list.key)}
						/>
						{#if list.key === 'episode_sources' && meta('episode_match_tolerance_seconds')}
							{@const tolerance = meta('episode_match_tolerance_seconds')!}
							<ConfigSchemaField
								field={{ ...tolerance, label: 'Episode match tolerance (seconds)' }}
								bind:value={values[tolerance.key]}
								config={values}
								context={config}
								{disabled}
							/>
						{/if}
						{#if list.key === 'music_sources'}
							<div
								class="list-row list-row-compact identity-card-planned identity-card-cddb"
								data-testid="identity-cddb"
								aria-disabled="true"
							>
								<div class="list-row-main">
									<div class="identity-card-row-head">
										<span class="identity-card-row-name">CDDB</span>
										<span class="chip chip-sm">Planned</span>
									</div>
									<div class="identity-card-row-note">Not built yet, so never ranked</div>
								</div>
							</div>
						{/if}
					</div>
				{/if}
			{/each}
		</div>
	</div>

	<div class="identity-card-step stack" data-step="4">
		{@render heading(4, 'Trust')}
		<div class="identity-card-trust">
			{#each TRUST as t (t.key)}
				{#if meta(t.key)}
					<div class="identity-card-option" id="setting-{t.key}" data-testid="setting-{t.key}">
						<label class="field field-row">
							<input
								type="checkbox"
								aria-label={t.label}
								aria-describedby="identity-help-trust"
								checked={Boolean(values[t.key])}
								disabled={off(t.key)}
								onchange={(e) => (values[t.key] = (e.currentTarget as HTMLInputElement).checked)}
							/>
							<span class="field-label">{t.label}</span>
						</label>
					</div>
				{/if}
			{/each}
		</div>
		<p class="field-help" id="identity-help-trust">
			When off, a match waits on the job page for you to confirm it and the disc is held with no countdown. Ripping ›
			Review first still holds every disc.
		</p>
	</div>

	{#if hasHints}
		<div class="identity-card-step stack" data-step="advanced" id="setting-disc_hint_sources">
			<span class="label-caps">Advanced</span>
			{#each IGNORE as box (box.hint)}
				<div class="identity-card-option">
					<label class="field field-row">
						<input
							type="checkbox"
							aria-label={box.label}
							aria-describedby="identity-help-ignore-{box.hint}"
							checked={isIgnored(box.hint)}
							disabled={off('disc_hint_sources')}
							onchange={(e) =>
								(values.disc_hint_sources = withHintIgnored(
									values,
									box.hint,
									(e.currentTarget as HTMLInputElement).checked
								))}
						/>
						<span class="field-label">{box.label}</span>
					</label>
					<p class="field-help" id="identity-help-ignore-{box.hint}">{box.help}</p>
				</div>
			{/each}
			<p class="field-help">
				For collections where the disc's own text is usually wrong. Fix a single disc from its job page instead.
			</p>
		</div>
	{/if}
</div>

<style>
	.identity-card-step {
		gap: 0.5rem;
		min-width: 0;
		border: 1px solid var(--color-border);
		border-radius: var(--radius-md);
		background: var(--color-surface);
		padding: 1rem;
	}
	.identity-card-rows {
		display: flex;
		flex-direction: column;
		gap: 0.5rem;
	}
	.identity-card-row-head {
		display: flex;
		flex-wrap: wrap;
		align-items: center;
		gap: 0.375rem;
	}
	.identity-card-row-name {
		font-size: 0.875rem;
		font-weight: 500;
		color: var(--color-text-secondary);
	}
	.identity-card-row-note,
	.identity-card-note {
		font-size: 0.8125rem;
		line-height: 1.25rem;
		color: var(--color-text-muted);
	}
	.identity-card-planned .identity-card-row-name {
		color: var(--color-text-muted);
	}
	.identity-card-planned {
		opacity: 0.75;
	}
	.identity-card-option {
		display: flex;
		flex-direction: column;
		gap: 0.25rem;
		scroll-margin-top: 6rem;
		border-radius: var(--radius-lg);
		transition: box-shadow var(--motion-base) var(--ease);
	}
	.identity-card-column {
		scroll-margin-top: 6rem;
		border-radius: var(--radius-lg);
		transition: box-shadow var(--motion-base) var(--ease);
	}
	/* Same fit-width grid as SchemaConfigForm's columns: side by side on
	   desktop, one column on a narrow panel without a media query. */
	.identity-card-columns {
		display: grid;
		grid-template-columns: repeat(auto-fit, minmax(min(18rem, 100%), 1fr));
		gap: 1.5rem;
	}
	.identity-card-cddb {
		grid-template-columns: 1fr;
		cursor: default;
		max-width: 36rem;
	}
	.identity-card-cddb:hover {
		background: transparent;
	}
	.identity-card-trust {
		display: flex;
		flex-direction: column;
		gap: 0.5rem;
	}
	.identity-card-heading {
		display: flex;
		align-items: center;
		gap: 0.5rem;
		font-size: 0.875rem;
		font-weight: 600;
		color: var(--color-text-secondary);
	}
	.identity-card-badge {
		display: inline-flex;
		align-items: center;
		justify-content: center;
		width: 1.375rem;
		height: 1.375rem;
		border-radius: 9999px;
		background: var(--color-primary-tint-3);
		color: var(--color-primary);
		font-size: 0.75rem;
		font-weight: 600;
		line-height: 1;
	}
	/* InterfaceSettings' segmented radiogroup, copied (scoped CSS). */
	.identity-card-segment {
		display: flex;
		align-self: flex-start;
		gap: 0.25rem;
		border-radius: var(--radius-lg);
		background: var(--color-primary-tint-1);
		padding: 0.25rem;
	}
	.identity-card-segment-btn {
		border-radius: var(--radius-md);
		padding: 0.375rem 0.75rem;
		font-size: 0.75rem;
		line-height: 1rem;
		font-weight: 500;
		color: var(--color-text-secondary);
		background: var(--color-primary-tint-2);
		cursor: pointer;
		transition:
			background-color var(--motion-fast) var(--ease),
			color var(--motion-fast) var(--ease);
	}
	.identity-card-segment-btn:hover {
		background: var(--color-primary-tint-3);
	}
	.identity-card-segment-btn[aria-checked='true'] {
		background: var(--color-primary);
		color: var(--color-on-primary);
	}
</style>
