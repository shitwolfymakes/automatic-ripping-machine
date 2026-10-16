<script lang="ts">
	import type { ConfigFieldMeta } from '$lib/types/api.gen';
	import {
		DISC_KIND_LABELS,
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
		{ key: 'episode_sources', heading: 'TV shows' }
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

{#snippet heading(title: string)}
	<h4 class="identity-card-heading">{title}</h4>
{/snippet}

<div class="identity-card stack stack-lg" data-testid="identity-card">
	<div class="identity-card-step stack" data-step="preview">
		<span class="identity-card-caption">Preview</span>
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

	<div class="identity-card-step stack" data-step="2">
		{@render heading('Disc database')}
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
						{#each db.chips as chip (chip)}<span class="chip identity-card-kind">{chip}</span>{/each}
					</div>
					<p class="field-help" id="identity-help-{db.key}">{db.description ?? field.help}</p>
				</div>
			{/if}
		{/each}
	</div>

	<div class="identity-card-step stack" data-step="3">
		{@render heading('Online lookup')}
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
					</div>
				{/if}
			{/each}
		</div>
	</div>

	<div class="identity-card-step stack" data-step="4">
		{@render heading('Trust')}
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
		<p class="field-help identity-card-footer" id="identity-help-trust">
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
			<p class="field-help identity-card-footer">
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
	.identity-card-caption {
		font-size: 1rem;
		font-weight: 600;
		color: var(--color-text);
	}
	.identity-card-heading {
		display: flex;
		align-items: center;
		gap: 0.75rem;
		margin-bottom: 0.75rem;
		font-size: 1.0625rem;
		font-weight: 600;
		color: var(--color-text);
	}
	.identity-card-row-head {
		display: flex;
		flex-wrap: wrap;
		align-items: center;
		gap: 0.5rem;
	}
	.identity-card-note {
		font-size: 0.8125rem;
		line-height: 1.25rem;
		color: var(--color-text-muted);
	}
	.identity-card-footer {
		margin-top: 0.25rem;
		border-top: 1px dashed var(--color-border);
		padding-top: 0.75rem;
		font-size: 0.9375rem;
		color: var(--color-text-muted);
	}
	/* Outline kind chips; scoped, so the global .chip stays as it is. */
	.identity-card-kind {
		border: 1px solid var(--color-border);
		border-radius: var(--radius-sm, 0.25rem);
		background: transparent;
		padding: 0.125rem 0.5rem;
		font-size: 0.8125rem;
		color: var(--color-text-secondary);
		cursor: default;
	}
	.identity-card-kind:hover {
		background: transparent;
	}
	.identity-card-option {
		display: flex;
		flex-direction: column;
		gap: 0.25rem;
		padding: 0.625rem 0;
		scroll-margin-top: 6rem;
		border-radius: var(--radius-lg);
		transition: box-shadow var(--motion-base) var(--ease);
	}
	.identity-card-option + .identity-card-option {
		border-top: 1px solid var(--color-border);
		border-radius: 0;
	}
	.identity-card-option .field-help:not(.identity-card-footer) {
		font-size: 0.875rem;
		color: var(--color-text-muted);
	}
	/* Each source list (Movies, TV shows) in its own box inside step 3. */
	.identity-card-column {
		min-width: 0;
		scroll-margin-top: 6rem;
		border: 1px solid var(--color-border);
		border-radius: var(--radius-md);
		background: color-mix(in srgb, var(--color-text) 3%, var(--color-surface));
		padding: 0.875rem 1rem;
		transition: box-shadow var(--motion-base) var(--ease);
	}
	/* Same fit-width grid as SchemaConfigForm's columns: side by side on
	   desktop, one column on a narrow panel without a media query. */
	.identity-card-columns {
		display: grid;
		grid-template-columns: repeat(auto-fit, minmax(min(18rem, 100%), 1fr));
		gap: 1.5rem;
	}
	.identity-card-trust {
		display: flex;
		flex-direction: column;
	}
	/* Segmented radiogroup: one outlined group, the selected kind filled. */
	.identity-card-segment {
		display: inline-flex;
		align-self: flex-start;
		border: 1px solid var(--color-border);
		border-radius: var(--radius-md);
		overflow: hidden;
		background: transparent;
	}
	.identity-card-segment-btn {
		padding: 0.5rem 1.125rem;
		font-size: 0.9375rem;
		font-weight: 500;
		line-height: 1.25rem;
		background: transparent;
		color: var(--color-text);
		cursor: pointer;
		transition:
			background-color var(--motion-fast) var(--ease),
			color var(--motion-fast) var(--ease);
	}
	.identity-card-segment-btn + .identity-card-segment-btn {
		border-left: 1px solid var(--color-border);
	}
	.identity-card-segment-btn:hover {
		background: color-mix(in srgb, var(--color-primary) 8%, transparent);
	}
	.identity-card-segment-btn[aria-checked='true'] {
		background: var(--color-primary);
		color: var(--color-primary-contrast, var(--color-on-primary));
	}
</style>
