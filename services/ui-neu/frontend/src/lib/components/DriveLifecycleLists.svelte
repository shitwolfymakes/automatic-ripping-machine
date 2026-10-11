<script lang="ts">
	import type { DriveView } from '$lib/types/api.gen';
	import { enrollDrive, ignoreDrive, unignoreDrive } from '$lib/api/drives';
	import { connectionLabel, driveTitle, mediaLabel, serialLabel } from '$lib/utils/drives';
	import { formatDateTime } from '$lib/utils/format';
	import Glyph from '$lib/components/Glyph.svelte';
	import StatusStrip from '$lib/components/StatusStrip.svelte';

	// Detected + ignored drives, shared by Settings > Drives and the setup
	// walkthrough's Drives step. Enrolling starts a ripper container, which
	// takes seconds and can fail per drive (setup spec §5.4), so each row
	// carries its own progress and error state.
	interface Props {
		detected: DriveView[];
		ignored: DriveView[];
		onchanged: () => void;
		/** Set when enrolling can't work right now (e.g. the ripper service is down). */
		enrollDisabledReason?: string | null;
	}
	let { detected, ignored, onchanged, enrollDisabledReason = null }: Props = $props();

	let ignoredOpen = $state(false);
	let busy = $state<Record<string, 'enroll' | 'other'>>({});
	let errors = $state<Record<string, string>>({});
	// Ids present at first render; anything detected later is flagged New.
	let firstSeen = $state<Set<string> | null>(null);

	$effect(() => {
		if (firstSeen === null) firstSeen = new Set(detected.map((d) => d.id));
	});

	const isNew = (d: DriveView) => firstSeen !== null && !firstSeen.has(d.id);

	async function run(id: string, kind: 'enroll' | 'other', action: () => Promise<unknown>) {
		busy = { ...busy, [id]: kind };
		const { [id]: _drop, ...rest } = errors;
		errors = rest;
		try {
			await action();
			onchanged();
		} catch (e) {
			errors = { ...errors, [id]: e instanceof Error ? e.message : 'Action failed' };
		} finally {
			const { [id]: _done, ...left } = busy;
			busy = left;
		}
	}
</script>

{#snippet row(d: DriveView, ignoredRow: boolean)}
	{@const serial = serialLabel(d)}
	{@const conn = connectionLabel(d)}
	{@const failure = errors[d.id] ?? (ignoredRow ? null : d.last_error)}
	<div
		data-testid={`${ignoredRow ? 'ignored' : 'detected'}-row-${d.id}`}
		class="drive-lifecycle-lists-row"
		data-new={!ignoredRow && isNew(d)}
		data-failed={!!failure}
	>
		<div class="drive-lifecycle-lists-head">
			<span class="drive-lifecycle-lists-icon" aria-hidden="true"><Glyph name="hard-drive" class="h-5 w-5" /></span>
			<div class="drive-lifecycle-lists-main">
				<div class="drive-lifecycle-lists-title-row">
					<span class="drive-lifecycle-lists-name">{driveTitle(d)}</span>
					{#if !ignoredRow && isNew(d)}<span class="badge badge-sm badge-info">New</span>{/if}
				</div>
				<code class="mono drive-lifecycle-lists-path">{d.device_path}{d.by_id_name ? `  ${d.by_id_name}` : ''}</code>
				<div class="cluster drive-lifecycle-lists-chips">
					{#if conn}<span class="chip chip-sm">{conn}</span>{/if}
					<span class="chip chip-sm"><Glyph name="disc-3" class="h-3 w-3" />{mediaLabel(d)}</span>
					<span class="drive-lifecycle-lists-serial" data-warn={serial.warn}>{serial.text}</span>
					<span class="drive-lifecycle-lists-seen">{d.last_seen_at ? formatDateTime(d.last_seen_at) : '-'}</span>
				</div>
			</div>
			<span class="drive-lifecycle-lists-actions">
				{#if ignoredRow}
					<button
						data-testid={`unignore-${d.id}`}
						disabled={!!busy[d.id]}
						onclick={() => run(d.id, 'other', () => unignoreDrive(d.id))}
						class="btn btn-sm">Un-ignore</button
					>
				{:else}
					<button
						data-testid={`ignore-${d.id}`}
						disabled={!!busy[d.id]}
						onclick={() => run(d.id, 'other', () => ignoreDrive(d.id))}
						class="btn btn-sm">Ignore</button
					>
				{/if}
				<button
					data-testid={`enroll-${d.id}`}
					disabled={!!busy[d.id] || !!enrollDisabledReason}
					onclick={() => run(d.id, 'enroll', () => enrollDrive(d.id))}
					class="btn btn-primary btn-sm"
				>
					{#if failure && !ignoredRow}<Glyph name="refresh" class="h-3.5 w-3.5" /> Retry{:else}Enroll{/if}
				</button>
			</span>
		</div>
		{#if busy[d.id] === 'enroll'}
			<StatusStrip tone="busy" title="Starting ripper..." detail="Usually under 10 seconds" progress />
		{:else if failure}
			<div data-testid={`lifecycle-error-${d.id}`}>
				<StatusStrip
					tone="danger"
					title="The ripper for this drive didn't start."
					detail="Other drives are not affected."
					message={failure}
				/>
			</div>
		{:else if !ignoredRow}
			<StatusStrip tone="muted" title="Not enrolled" detail="ARM leaves this drive alone until you enroll it." />
		{/if}
	</div>
{/snippet}

<div class="panel panel-compact stack drive-lifecycle-lists-panel" data-testid="drive-lifecycle-panel">
	<h3 class="drive-lifecycle-lists-title">Detected</h3>
	{#if enrollDisabledReason && detected.length > 0}
		<p class="alert alert-warning" data-testid="enroll-disabled-reason">{enrollDisabledReason}</p>
	{/if}
	{#if detected.length === 0}
		<p data-testid="detected-empty" class="drive-lifecycle-lists-empty">
			No unenrolled drives. Plug one in and it appears here on the next scan.
		</p>
	{:else}
		<div class="stack-sm stack">
			{#each detected as d (d.id)}{@render row(d, false)}{/each}
		</div>
	{/if}

	{#if ignored.length > 0}
		<button
			data-testid="ignored-toggle"
			aria-expanded={ignoredOpen}
			onclick={() => {
				ignoredOpen = !ignoredOpen;
			}}
			class="btn btn-link btn-sm drive-lifecycle-lists-ignored-toggle"
		>
			Ignored ({ignored.length})
			<Glyph name={ignoredOpen ? 'chevron-down' : 'chevron-right'} class="h-3.5 w-3.5" />
		</button>
		{#if ignoredOpen}
			<div class="stack-sm stack">
				{#each ignored as d (d.id)}{@render row(d, true)}{/each}
			</div>
		{/if}
	{/if}
</div>

<style>
	.drive-lifecycle-lists-panel {
		gap: 0.75rem;
	}
	.drive-lifecycle-lists-title {
		font-size: 0.875rem;
		line-height: 1.25rem;
		font-weight: 600;
		color: var(--color-text);
	}
	.drive-lifecycle-lists-empty {
		font-size: 0.875rem;
		line-height: 1.25rem;
		color: var(--color-text-faint);
	}
	/* :global: .dark is the app-level scheme class on <html>, outside this component's own template */
	:global(.dark) .drive-lifecycle-lists-empty {
		color: var(--color-text-muted);
	}
	.drive-lifecycle-lists-row {
		display: grid;
		gap: 0.75rem;
		border: 1px solid var(--color-border);
		border-radius: var(--radius-lg);
		padding: 0.875rem 1rem;
		font-size: 0.875rem;
	}
	.drive-lifecycle-lists-row[data-new='true'] {
		border-color: var(--color-primary);
		background: var(--color-primary-tint-1);
		animation: drive-lifecycle-lists-new 1.6s ease-out 1;
	}
	.drive-lifecycle-lists-row[data-failed='true'] {
		border-color: var(--color-danger);
	}
	@keyframes drive-lifecycle-lists-new {
		from {
			box-shadow: 0 0 0 6px var(--color-primary-tint-3);
		}
		to {
			box-shadow: 0 0 0 0 transparent;
		}
	}
	@media (prefers-reduced-motion: reduce) {
		.drive-lifecycle-lists-row[data-new='true'] {
			animation: none;
		}
	}
	.drive-lifecycle-lists-head {
		display: flex;
		align-items: flex-start;
		gap: 0.75rem;
	}
	.drive-lifecycle-lists-icon {
		flex: none;
		display: grid;
		place-items: center;
		width: 2.25rem;
		height: 2.25rem;
		border-radius: var(--radius-md);
		background: var(--color-primary-tint-2);
		color: var(--color-primary-text);
	}
	.drive-lifecycle-lists-main {
		flex: 1 1 auto;
		min-width: 0;
		display: grid;
		gap: 0.25rem;
	}
	.drive-lifecycle-lists-title-row {
		display: flex;
		flex-wrap: wrap;
		align-items: center;
		gap: 0.5rem;
	}
	.drive-lifecycle-lists-name {
		font-weight: 600;
		color: var(--color-text);
		overflow-wrap: anywhere;
	}
	.drive-lifecycle-lists-path {
		font-size: 0.75rem;
		color: var(--color-text-muted);
		overflow-wrap: anywhere;
		white-space: pre-wrap;
	}
	.drive-lifecycle-lists-chips {
		gap: 0.375rem 0.625rem;
		align-items: center;
	}
	.drive-lifecycle-lists-serial {
		font-size: 0.75rem;
		color: var(--color-text-muted);
	}
	.drive-lifecycle-lists-serial[data-warn='true'] {
		color: var(--color-on-warning-soft);
	}
	.drive-lifecycle-lists-seen {
		font-size: 0.75rem;
		color: var(--color-text-faint);
	}
	.drive-lifecycle-lists-actions {
		flex: none;
		display: flex;
		flex-wrap: wrap;
		justify-content: flex-end;
		gap: 0.5rem;
	}
	.drive-lifecycle-lists-ignored-toggle {
		display: inline-flex;
		align-items: center;
		gap: 0.25rem;
		font-size: 0.875rem;
		font-weight: 600;
		color: var(--color-text-secondary);
	}
	.drive-lifecycle-lists-ignored-toggle:hover {
		text-decoration: underline;
	}
	@media (max-width: 639px) {
		.drive-lifecycle-lists-head {
			flex-wrap: wrap;
		}
		.drive-lifecycle-lists-actions {
			width: 100%;
			justify-content: flex-start;
		}
	}
</style>
