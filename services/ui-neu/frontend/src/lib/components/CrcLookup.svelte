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

	const inputBase =
		'rounded-lg border border-primary/25 bg-primary/5 px-3 py-1.5 text-sm text-gray-900 focus:border-primary focus:outline-hidden focus:ring-1 focus:ring-primary dark:border-primary/30 dark:bg-primary/10 dark:text-white';
</script>

<div class="space-y-4">
	<!-- CRC64 hash display -->
	{#if crcId}
		<div class="flex items-center gap-2 text-sm">
			<span class="text-gray-500 dark:text-gray-400">CRC64:</span>
			<code class="rounded-sm bg-gray-100 px-2 py-0.5 font-mono text-xs text-gray-800 dark:bg-gray-800 dark:text-gray-300">{crcId}</code>
		</div>
	{/if}

	<!-- Lookup (no v3 endpoint) -->
	<div class="flex items-center gap-2">
		<p class="text-sm text-gray-500 dark:text-gray-400">CRC database lookup is not yet available in v3.</p>
		<ComingSoon label="Look up" feature="CRC lookup" />
	</div>

	<!-- Manual poster URL (LIVE: updateJobTitle) -->
	<hr class="border-gray-200 dark:border-gray-700" />
	<div class="space-y-3">
		<h4 class="text-sm font-semibold text-gray-700 dark:text-gray-300">Manual poster URL</h4>
		<label class="block">
			<span class="mb-1 block text-xs font-medium text-gray-500 dark:text-gray-400">Poster URL</span>
			<input type="text" bind:value={posterUrl} placeholder="https://..." class="w-full {inputBase}" />
		</label>
		<div class="flex items-center gap-2">
			<button
				onclick={handleApply}
				disabled={applying}
				class="rounded-lg px-3 py-1.5 text-sm font-medium bg-green-600 text-white hover:bg-green-700 dark:bg-green-500 dark:hover:bg-green-600 disabled:opacity-50 transition-colors"
			>
				{applying ? 'Applying...' : 'Apply to Job'}
			</button>
			{#if applyFeedback}
				<span class="text-xs {applyFeedback.type === 'success' ? 'text-green-600 dark:text-green-400' : 'text-red-600 dark:text-red-400'}">
					{applyFeedback.message}
				</span>
			{/if}
		</div>
	</div>

	<!-- Submit (no v3 endpoint) -->
	<hr class="border-gray-200 dark:border-gray-700" />
	<div class="space-y-3">
		<h4 class="text-sm font-semibold text-gray-700 dark:text-gray-300">Submit to CRC Database</h4>
		<ComingSoon label="Submit to CRC Database" feature="CRC submit" />
	</div>
</div>
