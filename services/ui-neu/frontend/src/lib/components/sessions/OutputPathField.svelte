<script lang="ts">
	import type { MediaType } from '$lib/types/api.gen';
	import { previewTemplate } from '$lib/api/sessions';

	interface Props {
		value: string;
		mediaType: MediaType;
		onchange: (v: string) => void;
		has_transcode_preset?: boolean;
		id?: string;
		disabled?: boolean;
	}

	let { value, mediaType, onchange, has_transcode_preset, id, disabled = false }: Props = $props();

	// Valid tokens per media type
	const TOKENS: Record<MediaType, string[]> = {
		movie: ['title', 'year', 'track', 'duration_human', 'transcode_slug', 'ext'],
		tv: ['show', 'year', 'season', 'disc', 'track', 'episode', 'episode_title', 'duration_human', 'transcode_slug', 'ext'],
		music: ['artist', 'album', 'disc', 'track', 'track_title', 'transcode_slug', 'ext'],
		data: ['title'],
		iso: ['title', 'year', 'ext'],
	};

	let expansion = $state<string | null>(null);
	let previewError = $state<string | null>(null);
	// Non-reactive — just a handle for clearTimeout; must NOT be $state (would cause effect cycles)
	let debounceTimer: ReturnType<typeof setTimeout> | null = null;

	$effect(() => {
		// Access reactive values to track them
		const template = value;
		const type = mediaType;

		if (debounceTimer !== null) {
			clearTimeout(debounceTimer);
		}

		if (!template) {
			expansion = null;
			previewError = null;
			return;
		}

		debounceTimer = setTimeout(async () => {
			try {
				const body: { template: string; media_type: MediaType; has_transcode_preset?: boolean } = {
					template,
					media_type: type,
				};
				if (has_transcode_preset !== undefined) {
					body.has_transcode_preset = has_transcode_preset;
				}
				const result = await previewTemplate(body);
				expansion = result.expansion;
				previewError = null;
			} catch (err) {
				previewError = err instanceof Error ? err.message : String(err);
				expansion = null;
			}
		}, 300);

		return () => {
			if (debounceTimer) clearTimeout(debounceTimer);
		};
	});

	function insertToken(token: string) {
		const newValue = value + `{${token}}`;
		onchange(newValue);
	}

	let tokens = $derived(TOKENS[mediaType] ?? []);
</script>

<div class="stack stack-sm">
	<!-- Text input -->
	<input
		type="text"
		{id}
		class="mono field-control output-path-field-input"
		value={value}
		oninput={(e) => onchange((e.target as HTMLInputElement).value)}
		{disabled}
	/>

	<!-- Token chips (hidden when read-only — nothing to insert) -->
	{#if !disabled}
		<div class="cluster output-path-field-tokens">
			{#each tokens as token (token)}
				<button
					type="button"
					onclick={() => insertToken(token)}
					class="chip mono output-path-field-token"
				>
					{`{${token}}`}
				</button>
			{/each}
		</div>
	{/if}

	<!-- Live preview -->
	{#if expansion !== null}
		<div class="output-path-field-preview">
			<span class="output-path-field-preview-label">LIVE PREVIEW</span>
			<span class="mono output-path-field-preview-value">{expansion}</span>
		</div>
	{/if}
	{#if previewError !== null}
		<div class="output-path-field-preview output-path-field-preview-error">
			<span class="output-path-field-preview-label output-path-field-error-label">PREVIEW ERROR</span>
			<span class="mono output-path-field-preview-value output-path-field-error-value">{previewError}</span>
		</div>
	{/if}
</div>

<style>
	/* original: font-mono text-sm (0.875rem/1.25rem) - .field-control's own
	   font-size/line-height (also 0.875rem/1.25rem) already match, so .mono
	   only needs to add the family; nothing to restate here. */
	.output-path-field-input { width: 100%; }
	.output-path-field-tokens { gap: 0.375rem; }
	/* original chips: rounded bg-primary/10 px-2 py-0.5 font-mono text-xs
	   font-medium text-primary hover:bg-primary/20 - chip's own radius
	   (--radius-sm, matches rounded's default) and background/hover tokens
	   already match; only the font (mono, not chip's default sans) and
	   weight need restating. */
	.output-path-field-token { line-height: 1rem; font-weight: 500; }
	/* original: rounded-md bg-gray-50 px-3 py-2 dark:bg-gray-800/50 - a plain
	   neutral surface with no equivalent block; --color-primary-tint-1 is the
	   nearest role (panel-section's own background) since no neutral
	   surface token exists in spec 5.1. */
	.output-path-field-preview { border-radius: var(--radius-md); background: var(--color-primary-tint-1); padding: 0.5rem 0.75rem; }
	/* the error variant used bg-red-50/dark:bg-red-900/20 instead of the
	   neutral gray - the danger-soft token pair reproduces that. */
	.output-path-field-preview-error { background: var(--color-danger-soft); }
	/* original labels: text-xs font-semibold uppercase tracking-wide
	   (12px/16px, tracking 0.025em) - NOT .eyebrow's metrics (10.5px,
	   tracking 0.12em; that block is reserved for the arbitrary
	   text-[10.5px] tracking-[0.12em] string per the migration reference),
	   so restated in full here rather than borrowed from a block that looks
	   similar but measures differently. */
	.output-path-field-preview-label { margin-right: 0.5rem; font-size: 0.75rem; line-height: 1rem; font-weight: 600; letter-spacing: 0.025em; text-transform: uppercase; color: var(--color-text-faint); }
	/* original error label: text-red-500, no dark: variant (same shade both
	   modes) - --color-danger is red-600/red-400 across modes, the same
	   accepted mode-dependent collapse the migration reference documents for
	   the danger family generally. */
	.output-path-field-error-label { color: var(--color-danger); }
	/* original preview/error value text: font-mono text-sm (0.875rem/1.25rem),
	   break-all (not overflow-wrap's word-preferring break-word) - reproduced
	   exactly so long output-path strings wrap at the same column as before
	   (a prior sibling task's regression here is why this is spelled out). */
	.output-path-field-preview-value { word-break: break-all; font-size: 0.875rem; line-height: 1.25rem; color: var(--color-text-secondary); }
	.output-path-field-error-value { color: var(--color-danger); }
</style>
