<script lang="ts">
	import type { DriveView } from '$lib/types/api.gen';
	import { enrollDrive, ignoreDrive, unignoreDrive } from '$lib/api/drives';
	import { serialLabel } from '$lib/utils/drives';
	import { formatDateTime } from '$lib/utils/format';

	interface Props { detected: DriveView[]; ignored: DriveView[]; onchanged: () => void }
	let { detected, ignored, onchanged }: Props = $props();

	let ignoredOpen = $state(false);
	let busy = $state<string | null>(null);
	let error = $state<string | null>(null);

	async function run(id: string, action: () => Promise<unknown>) {
		busy = id;
		error = null;
		try {
			await action();
			onchanged();
		} catch (e) {
			error = e instanceof Error ? e.message : 'Action failed';
		} finally {
			busy = null;
		}
	}
</script>

{#snippet row(d: DriveView, ignoredRow: boolean)}
	{@const serial = serialLabel(d)}
	<div data-testid={`${ignoredRow ? 'ignored' : 'detected'}-row-${d.id}`} class="flex flex-wrap items-center gap-x-3 gap-y-1 drive-lifecycle-lists-row">
		<span class="drive-lifecycle-lists-name">{d.model ?? d.hostname}</span>
		<span class="drive-lifecycle-lists-serial" data-warn={serial.warn}>{serial.text}</span>
		<code class="mono drive-lifecycle-lists-path">{d.device_path}</code>
		<span class="drive-lifecycle-lists-seen">{d.last_seen_at ? formatDateTime(d.last_seen_at) : '-'}</span>
		<span class="ml-auto flex gap-2">
			{#if ignoredRow}
				<button data-testid={`unignore-${d.id}`} disabled={busy === d.id} onclick={() => run(d.id, () => unignoreDrive(d.id))} class="btn btn-sm">Un-ignore</button>
			{:else}
				<button data-testid={`ignore-${d.id}`} disabled={busy === d.id} onclick={() => run(d.id, () => ignoreDrive(d.id))} class="btn btn-sm">Ignore</button>
			{/if}
			<button data-testid={`enroll-${d.id}`} disabled={busy === d.id} onclick={() => run(d.id, () => enrollDrive(d.id))} class="btn btn-primary btn-sm">Enroll</button>
		</span>
	</div>
{/snippet}

<div class="panel panel-compact stack drive-lifecycle-lists-panel" data-testid="drive-lifecycle-panel">
	<h3 class="drive-lifecycle-lists-title">Detected</h3>
	{#if error}
		<p data-testid="lifecycle-error" class="field-error">{error}</p>
	{/if}
	{#if detected.length === 0}
		<p data-testid="detected-empty" class="drive-lifecycle-lists-empty">No unenrolled drives. Plug one in and it appears here on the next scan.</p>
	{:else}
		<div class="stack-sm stack">
			{#each detected as d (d.id)}{@render row(d, false)}{/each}
		</div>
	{/if}

	{#if ignored.length > 0}
		<button data-testid="ignored-toggle" aria-expanded={ignoredOpen} onclick={() => { ignoredOpen = !ignoredOpen; }} class="btn btn-link btn-sm drive-lifecycle-lists-ignored-toggle">
			Ignored ({ignored.length}) {ignoredOpen ? '▾' : '▸'}
		</button>
		{#if ignoredOpen}
			<div class="stack-sm stack">
				{#each ignored as d (d.id)}{@render row(d, true)}{/each}
			</div>
		{/if}
	{/if}
</div>

<style>
	/* the outer panel's rows were space-y-3 (0.75rem) - between stack-sm's
	   0.5rem and stack's own 1rem, so neither modifier matches exactly. */
	.drive-lifecycle-lists-panel { gap: 0.75rem; }
	.drive-lifecycle-lists-title { font-size: 0.875rem; line-height: 1.25rem; font-weight: 600; color: var(--color-text); }
	/* the original empty-state note was text-sm text-gray-400
	   (0.875rem/1.25rem), not panel-hint's 0.75rem - and it carried no
	   dark: variant, so it stayed gray-400 in both modes. --color-text-faint
	   IS gray-400 in light but steps down to gray-500 in dark, so name the
	   role that is gray-400 in dark (--color-text-muted) there instead of
	   inventing a token. */
	.drive-lifecycle-lists-empty { font-size: 0.875rem; line-height: 1.25rem; color: var(--color-text-faint); }
	:global(.dark) .drive-lifecycle-lists-empty { color: var(--color-text-muted); } /* :global: .dark is the app-level scheme class on <html>, outside this component's own template */
	.drive-lifecycle-lists-row { border: 1px solid var(--color-border); border-radius: var(--radius-lg); padding: 0.5rem 0.75rem; font-size: 0.875rem; }
	.drive-lifecycle-lists-name { font-weight: 500; color: var(--color-text); }
	.drive-lifecycle-lists-serial { color: var(--color-text-muted); }
	.drive-lifecycle-lists-serial[data-warn="true"] { color: var(--color-on-warning-soft); }
	.drive-lifecycle-lists-path { font-size: 0.75rem; color: var(--color-text-muted); }
	.drive-lifecycle-lists-seen { font-size: 0.75rem; color: var(--color-text-faint); }
	/* the row buttons were never .btn's default outlined look - a plain
	   primary-tinted pill (Ignore/Un-ignore) or a stronger fill (Enroll),
	   both smaller radius than .btn-sm. */
	.drive-lifecycle-lists-row .btn { border: 0; min-height: auto; border-radius: var(--radius-md); background: transparent; color: var(--color-primary-text); }
	.drive-lifecycle-lists-row .btn:hover { background: var(--color-primary-tint-1); }
	.drive-lifecycle-lists-row .btn-primary { background: var(--color-primary-tint-2); color: var(--color-primary-text); }
	.drive-lifecycle-lists-row .btn-primary:hover { background: var(--color-primary-tint-3); }
	.drive-lifecycle-lists-ignored-toggle { font-size: 0.875rem; font-weight: 600; color: var(--color-text-secondary); }
	.drive-lifecycle-lists-ignored-toggle:hover { text-decoration: underline; }
</style>
