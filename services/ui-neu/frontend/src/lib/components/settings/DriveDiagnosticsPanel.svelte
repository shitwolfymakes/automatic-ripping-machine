<script lang="ts">
	import { plural } from '$lib/utils/plural';
	import { slide } from 'svelte/transition';
	import Glyph from '$lib/components/shared/Glyph.svelte';
	import { formatDateTime } from '$lib/utils/format';
	import type { DriveDiagnostics } from '$lib/stores/drive-diagnostics.svelte';

	interface Props {
		diagnostics: DriveDiagnostics;
	}

	let { diagnostics }: Props = $props();
</script>

<hr class="settings-page-diag-divider" />
<div data-diag>
	<button onclick={diagnostics.toggle} aria-expanded={diagnostics.open} class="btn settings-page-diag-toggle">
		<Glyph name="shield-check" />
		Drive Diagnostics
		<Glyph name="chevron-down" class="chevron ml-auto" />
	</button>

	{#if diagnostics.open}
		<div class="panel-section settings-page-diag-panel" transition:slide={{ duration: 200 }}>
			<div class="mb-2.5 flex items-center justify-between">
				<button
					onclick={diagnostics.run}
					disabled={diagnostics.running}
					data-busy={diagnostics.running}
					class="btn settings-page-diag-run"
				>
					<Glyph name="refresh" class="settings-page-diag-run-icon" />
					{diagnostics.running ? 'Running...' : 'Run Check'}
				</button>
				{#if diagnostics.lastRun}
					<span class="settings-page-diag-last-run">Last run: {diagnostics.lastRun}</span>
				{/if}
				{#if diagnostics.error}
					<span class="settings-page-diag-error">{diagnostics.error}</span>
				{/if}
			</div>

			{#if diagnostics.result}
				{@const system = diagnostics.result.system ?? []}
				<!-- The backend decides which drives are unhealthy; a healthy drive's notes are informational. -->
				{@const unhealthy = diagnostics.result.drives.filter((d) => !d.healthy)}
				{#if system.length > 0}
					<div class="alert alert-warning mb-2 settings-page-diag-system" data-testid="diag-system">
						{#each system as note, i (i)}
							<div>{note}</div>
						{/each}
					</div>
				{/if}

				<!-- Status bar -->
				<div
					class="alert {unhealthy.length > 0 || system.length > 0
						? 'alert-warning'
						: 'alert-success'} mb-2 flex flex-wrap items-center gap-3"
				>
					<span class="settings-page-diag-count">
						{diagnostics.result.drives.length}
						{plural(diagnostics.result.drives.length, 'drive')}
					</span>
					<span class="alert-title">
						{unhealthy.length > 0 || system.length > 0 ? 'Issues Found' : 'All OK'}
					</span>
				</div>

				<!-- Every drive, healthy or not -->
				{#each diagnostics.result.drives as diag (diag.id)}
					{@const flagged = unhealthy.includes(diag)}
					<div data-testid="diag-drive-{diag.id}" class="settings-page-diag-drive" data-flagged={flagged}>
						<div class="flex flex-wrap items-center gap-x-2 gap-y-1 settings-page-diag-drive-row">
							<code class="mono settings-page-diag-drive-path">{diag.device_path}</code>
							<span class="badge badge-sm">{diag.lifecycle}</span>
							<span data-warn={!diag.present}>{diag.present ? 'connected' : 'not connected'}</span>
							{#if diag.container}<span>container: {diag.container}</span>{/if}
							{#if diag.status}<span>ripper: {diag.status}</span>{/if}
							{#if diag.media_status}<span>media: {diag.media_status.replace('_', ' ')}</span>{/if}
							{#if diag.media_status_at}<span class="settings-page-diag-heartbeat"
									>heartbeat {formatDateTime(diag.media_status_at)}</span
								>{/if}
							{#if !flagged}<span class="ml-auto settings-page-diag-ok">OK</span>{/if}
						</div>
						{#if diag.last_error}
							<div class="field-error mt-1">{diag.last_error}</div>
						{/if}
						{#each diag.notes as note, i (i)}
							<div class="mt-1 flex items-start gap-1.5 settings-page-diag-note">
								{#if note === 'ignored'}
									<span class="settings-page-diag-ignored">ignored</span>
								{:else if diag.healthy}
									<span class="settings-page-diag-ignored">{note}</span>
								{:else}
									<Glyph name="warning" class="mt-0.5 h-3 w-3 flex-shrink-0 settings-page-diag-warn-icon" />
									<span class="settings-page-diag-warn-text">{note}</span>
								{/if}
							</div>
						{/each}
						{#if diag.notes.length === 0 && !diag.healthy}
							<div class="settings-page-diag-warn-text mt-1">unhealthy</div>
						{/if}
					</div>
				{/each}
			{:else if !diagnostics.running}
				<p class="settings-page-diag-empty">Click "Run Check" to scan drives and udev configuration.</p>
			{/if}
		</div>
	{/if}
</div>

<style>
	/* Drive Diagnostics disclosure: a full-width outlined toggle
	   button over a collapsible detail panel, none of it matching .panel's
	   metrics (this reuses .panel-section's tint but at its own padding). */
	/* the original `<hr class="my-2">` sat in a `space-y-6` (margin) stack:
	   Tailwind v4's zero-specificity space-y rule lost to my-2, so the hr's
	   own 0.5rem margin-top collapsed into the panel's 1.5rem margin-bottom
	   (24px above) and its 0.5rem margin-bottom stood alone (8px below,
	   the diag div being the last child and so getting no space-y margin).
	   .stack-lg's flex gap never collapses, so cancel 1rem below the hr to
	   reproduce the original 24px/8px split. */
	.settings-page-diag-divider {
		margin: 0 0 -1rem;
		border: 0;
		border-top: 1px solid var(--color-text);
		opacity: 0.2;
	}
	/* the original border was border-primary/15 (--color-border), lighter
	   than .btn's default border-primary-strong. */
	/* px-3.5 py-2.5 (0.875rem/0.625rem), not .btn's own 1rem/0.5rem - 4px
	   taller than .btn's default, and the toggle sets the height of
	   everything below it on the Drives tab. */
	.settings-page-diag-toggle {
		width: 100%;
		justify-content: flex-start;
		gap: 0.5rem;
		padding: 0.625rem 0.875rem;
		border-color: var(--color-border);
		background: var(--color-primary-tint-1);
	}
	/* the original chevron flipped a full 180deg (open = pointing up);
	   .btn's shared .chevron rule only rotates 90deg, tuned for a
	   right-pointing chevron that turns to point down. */
	/* :global: .chevron is rendered by the child Glyph component, outside this component's own scoped template */
	.settings-page-diag-toggle[aria-expanded='true'] :global(.chevron) {
		transform: rotate(180deg);
	}
	.settings-page-diag-panel {
		margin-top: 0.625rem;
		padding: 0.75rem;
	}
	/* the original button was a tinted fill (bg-primary/15, no border), not
	   .btn's default outlined look. */
	.settings-page-diag-run {
		padding: 0.375rem 0.875rem;
		border-color: transparent;
		background: var(--color-primary-tint-3);
		color: var(--color-primary-text);
	}
	.settings-page-diag-run:hover {
		background: color-mix(in srgb, var(--color-primary) 25%, transparent);
	}
	/* :global: class forwarded onto Glyph's internal <svg>, outside this component's own template */
	button[data-busy='true'] :global(.settings-page-diag-run-icon) {
		animation: settings-page-spin 1s linear infinite;
	}
	@keyframes settings-page-spin {
		to {
			transform: rotate(360deg);
		}
	}
	.settings-page-diag-last-run {
		font-size: 0.625rem;
		color: var(--color-text-faint);
	}
	/* the original diagError span was text-sm (0.875rem/1.25rem), not
	   field-error's 0.75rem. */
	.settings-page-diag-error {
		font-size: 0.875rem;
		line-height: 1.25rem;
		color: var(--color-danger);
	}
	.settings-page-diag-system {
		font-size: 0.75rem;
		padding: 0.625rem;
	}
	.settings-page-diag-count {
		font-size: 0.75rem;
		color: var(--color-text-muted);
	}
	.settings-page-diag-drive {
		margin-bottom: 0.375rem;
		border: 1px solid var(--color-border);
		border-radius: var(--radius-lg);
		padding: 0.625rem;
	}
	.settings-page-diag-drive[data-flagged='true'] {
		border-color: color-mix(in srgb, var(--color-warning) 30%, transparent);
		background: var(--color-warning-soft);
	}
	.settings-page-diag-drive-row {
		font-size: 0.75rem;
		color: var(--color-text-secondary);
	}
	.settings-page-diag-drive-path {
		font-weight: 500;
		color: var(--color-text);
	}
	.settings-page-diag-drive-row [data-warn='true'] {
		color: var(--color-on-warning-soft);
	}
	.settings-page-diag-heartbeat {
		color: var(--color-text-faint);
	}
	.settings-page-diag-ok {
		font-weight: 500;
		color: var(--color-success);
	}
	.settings-page-diag-note {
		font-size: 0.75rem;
	}
	.settings-page-diag-ignored {
		color: var(--color-text-faint);
	}
	/* :global: forwarded onto Glyph's internal <svg>, as above. */
	:global(.settings-page-diag-warn-icon) {
		color: var(--color-warning);
	}
	.settings-page-diag-warn-text {
		color: var(--color-on-warning-soft);
	}
	.settings-page-diag-empty {
		text-align: center;
		font-size: 0.75rem;
		color: var(--color-text-faint);
	}
</style>
