<script lang="ts">
	import type { JobView } from '$lib/types/api.gen';
	import { updateJobTitle } from '$lib/api/jobs';
	import ComingSoon from './ComingSoon.svelte';

	// ---------------------------------------------------------------------------
	// MISSING in v3 — CRC lookup / submission have no v3 endpoint. The lookup
	// (fetchCrcLookup) and submit (submitToCrcDb) actions are stubbed and gated
	// OFF via the ComingSoon treatment. The only LIVE control here is the
	// title-apply (updateJobTitle → PATCH /api/jobs/{id}), which sets the manual
	// poster URL on the job.
	// ---------------------------------------------------------------------------

	interface Props {
		job: JobView;
		// CRC / video-type metadata have no JobView equivalent (BFF-only); accept
		// them as optional props so the screen still type-checks.
		crcId?: string | null;
		videoType?: string | null;
		imdbId?: string | null;
		onapply?: () => void;
	}

	let { job, crcId = null, onapply }: Props = $props();

	let applying = $state(false);
	let applyFeedback = $state<{ type: 'success' | 'error'; message: string } | null>(null);

	let posterUrl = $state(job.poster_url ?? '');

	async function handleApply() {
		applying = true;
		applyFeedback = null;
		try {
			// v3 only accepts poster_url_manual on the job.
			await updateJobTitle(job.id, { poster_url_manual: posterUrl.trim() || null });
			applyFeedback = { type: 'success', message: 'Job updated' };
			onapply?.();
		} catch (e) {
			applyFeedback = { type: 'error', message: e instanceof Error ? e.message : 'Update failed' };
		} finally {
			applying = false;
		}
	}


</script>

<div class="stack">
	<!-- CRC64 hash display -->
	{#if crcId}
		<div class="flex items-center gap-2 crc-lookup-hash-row">
			<span class="crc-lookup-label">CRC64:</span>
			<code class="mono crc-lookup-hash">{crcId}</code>
		</div>
	{/if}

	<!-- Lookup (no v3 endpoint) -->
	<div class="flex items-center gap-2">
		<p class="field-help">CRC database lookup is not yet available in v3.</p>
		<ComingSoon label="Look up" feature="CRC lookup" />
	</div>

	<!-- Manual poster URL (LIVE: updateJobTitle) -->
	<hr class="crc-lookup-divider" />
	<div class="stack">
		<h4 class="crc-lookup-heading">Manual poster URL</h4>
		<label class="field">
			<span class="field-label">Poster URL</span>
			<input type="text" bind:value={posterUrl} placeholder="https://..." />
		</label>
		<div class="flex items-center gap-2">
			<button
				onclick={handleApply}
				disabled={applying}
				class="btn crc-lookup-success-btn"
			>
				{applying ? 'Applying...' : 'Apply to Job'}
			</button>
			{#if applyFeedback}
				<span class="crc-lookup-feedback" data-tone={applyFeedback.type}>
					{applyFeedback.message}
				</span>
			{/if}
		</div>
	</div>

	<!-- Submit (no v3 endpoint) -->
	<hr class="crc-lookup-divider" />
	<div class="stack">
		<h4 class="crc-lookup-heading">Submit to CRC Database</h4>
		<ComingSoon label="Submit to CRC Database" feature="CRC submit" />
	</div>
</div>

<style>
	.crc-lookup-hash-row { font-size: 0.875rem; line-height: 1.25rem; }
	.crc-lookup-label { color: var(--color-text-muted); }
	.crc-lookup-hash { border-radius: var(--radius-sm); background: var(--color-primary-tint-2); padding: 0.125rem 0.5rem; font-size: 0.75rem; line-height: 1rem; color: var(--color-text-secondary); }
	.crc-lookup-divider { border: 0; border-top: 1px solid var(--color-border); }
	.crc-lookup-heading { font-size: 0.875rem; line-height: 1.25rem; font-weight: 600; color: var(--color-text-secondary); }
	.crc-lookup-success-btn { border: 0; padding: 0.375rem 0.75rem; background: var(--color-success); color: var(--color-on-primary); }
	.crc-lookup-success-btn:hover { filter: brightness(0.9); }
	.crc-lookup-feedback { font-size: 0.75rem; line-height: 1rem; }
	.crc-lookup-feedback[data-tone="success"] { color: var(--color-success); }
	.crc-lookup-feedback[data-tone="error"] { color: var(--color-danger); }
</style>
