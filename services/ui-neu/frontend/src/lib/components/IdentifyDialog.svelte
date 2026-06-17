<script lang="ts">
	import { resolveJob } from '$lib/api/jobs';
	import type { JobView, ResolveResponse } from '$lib/types/api.gen';

	let {
		job,
		onclose,
		onidentified
	}: {
		job: JobView;
		onclose: () => void;
		onidentified: (resp: ResolveResponse) => void;
	} = $props();

	// `isCd` switches the form body between the two-field (title + year)
	// video shape and the structured-music shape. The music path template
	// requires {artist}, {album}, and per-track {track_title} — none of
	// which a title-only resolve can populate.
	const isCd = $derived(job.disc_type === 'cd');

	// `isEditMode` distinguishes the "auto-identify failed, please fill in"
	// case (status awaiting_user_id / ripped_awaiting_identify) from the
	// "auto-identify landed wrong metadata, correct it" case (post-rip
	// status). The submit endpoint is the same; only the copy differs.
	const isEditMode = $derived(
		!['awaiting_user_id', 'ripped_awaiting_identify'].includes(job.status)
	);

	// CD-only: per-track count comes from the preserved scan_result on the
	// job's metadata_json. If it's absent we skip the per-track inputs and
	// show a helper line; the resolve still succeeds.
	const scanTrackCount = $derived(
		Array.isArray(
			(job.metadata_json?.scan_result as { titles?: unknown[] } | undefined)?.titles
		)
			? ((job.metadata_json.scan_result as { titles: unknown[] }).titles.length as number)
			: 0
	);

	// Video / DVD / BD / data fields.
	let title = $state(job.title ?? '');
	let year = $state<number | null>(job.year);

	// CD fields.
	let album = $state(job.title ?? '');
	let artist = $state('');
	let trackTitles = $state<string[]>(Array.from({ length: scanTrackCount }, () => ''));

	let submitting = $state(false);
	let error = $state<string | null>(null);

	const canSubmit = $derived(
		submitting
			? false
			: isCd
				? album.trim().length > 0 && artist.trim().length > 0
				: title.trim().length > 0
	);

	async function submit(event: Event): Promise<void> {
		event.preventDefault();
		if (!canSubmit) return;
		submitting = true;
		error = null;
		try {
			const metadata = isCd
				? {
						artist: artist.trim(),
						album: album.trim(),
						tracks: trackTitles.map((t) => ({ title: t.trim() }))
					}
				: undefined;
			const resp = await resolveJob(job.id, {
				title: isCd ? album.trim() : title.trim(),
				year: year ?? null,
				metadata
			});
			onidentified(resp);
		} catch (e) {
			error = e instanceof Error ? e.message : 'Identify failed';
		} finally {
			submitting = false;
		}
	}
</script>

<div class="fixed inset-0 z-50 flex items-center justify-center">
	<button
		type="button"
		class="absolute inset-0 bg-black/50"
		aria-label="Close dialog"
		onclick={onclose}
	></button>

	<div
		class="relative z-10 w-full max-w-xl rounded-lg bg-surface p-6 shadow-xl dark:bg-surface-dark"
		data-dialog
		role="dialog"
		aria-modal="true"
		aria-labelledby="identify-dialog-title"
	>
		<h3
			id="identify-dialog-title"
			class="text-lg font-semibold text-gray-900 dark:text-white"
		>
			{isEditMode ? 'Edit identity' : 'Identify this disc'}
		</h3>

		{#if error}
			<p class="mt-2 text-sm text-red-600 dark:text-red-400" data-testid="identify-error">
				{error}
			</p>
		{/if}

		{#if isEditMode}
			<p class="mt-2 text-sm text-gray-600 dark:text-gray-400">
				Update the title, year, and metadata for this job. Status stays as-is. Existing
				transcoded files keep their original filenames — re-apply a session if you want new
				outputs under the corrected name.
			</p>
		{:else}
			<p class="mt-2 text-sm text-gray-600 dark:text-gray-400">
				The disc on drive <code class="font-mono">{job.drive_id}</code> couldn't be identified
				automatically. Fill in the details so ARM can proceed. Any session you've already applied
				will pick up the resolved metadata and queue its transcode tasks.
			</p>
		{/if}

		<form class="mt-4" onsubmit={submit}>
			{#if isCd}
				<div class="mb-3 flex gap-3">
					<label class="flex-[2] text-sm font-medium text-gray-700 dark:text-gray-300">
						Album
						<input
							bind:value={album}
							type="text"
							required
							data-testid="identify-album"
							disabled={submitting}
							class="mt-1 w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 dark:border-gray-600 dark:bg-gray-800 dark:text-white"
						/>
					</label>
					<label class="flex-1 text-sm font-medium text-gray-700 dark:text-gray-300">
						Year
						<input
							bind:value={year}
							type="number"
							min="1888"
							max="2100"
							data-testid="identify-year"
							disabled={submitting}
							class="mt-1 w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 dark:border-gray-600 dark:bg-gray-800 dark:text-white"
						/>
					</label>
				</div>
				<div class="mb-3">
					<label class="text-sm font-medium text-gray-700 dark:text-gray-300">
						Artist
						<input
							bind:value={artist}
							type="text"
							required
							data-testid="identify-artist"
							disabled={submitting}
							class="mt-1 w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 dark:border-gray-600 dark:bg-gray-800 dark:text-white"
						/>
					</label>
				</div>
				{#if scanTrackCount > 0}
					<div class="mb-3">
						<div class="mb-1 text-sm text-gray-500 dark:text-gray-400">Track titles</div>
						{#each trackTitles as _t, idx (idx)}
							<div class="mb-1 flex items-center gap-2">
								<span class="w-8 text-right text-sm text-gray-500 dark:text-gray-400">
									{String(idx + 1).padStart(2, '0')}
								</span>
								<input
									bind:value={trackTitles[idx]}
									type="text"
									data-testid={`identify-track-${idx + 1}`}
									disabled={submitting}
									class="flex-1 rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 dark:border-gray-600 dark:bg-gray-800 dark:text-white"
								/>
							</div>
						{/each}
					</div>
				{:else}
					<p class="mb-3 text-sm text-gray-500 dark:text-gray-400">
						Track count couldn't be determined from the scan; transcoded filenames will fall back
						to generic names.
					</p>
				{/if}
			{:else}
				<div class="mb-3 flex gap-3">
					<label class="flex-[2] text-sm font-medium text-gray-700 dark:text-gray-300">
						Title
						<input
							bind:value={title}
							type="text"
							required
							data-testid="identify-title"
							disabled={submitting}
							class="mt-1 w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 dark:border-gray-600 dark:bg-gray-800 dark:text-white"
						/>
					</label>
					<label class="flex-1 text-sm font-medium text-gray-700 dark:text-gray-300">
						Year
						<input
							bind:value={year}
							type="number"
							min="1888"
							max="2100"
							data-testid="identify-year"
							disabled={submitting}
							class="mt-1 w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 dark:border-gray-600 dark:bg-gray-800 dark:text-white"
						/>
					</label>
				</div>
			{/if}

			<div class="mt-4 flex justify-end gap-3">
				<button
					type="button"
					onclick={onclose}
					disabled={submitting}
					class="rounded-lg px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-100 dark:text-gray-300 dark:hover:bg-gray-700"
				>
					Cancel
				</button>
				<button
					type="submit"
					disabled={!canSubmit}
					data-testid="identify-submit"
					class="rounded-lg px-4 py-2 text-sm font-medium confirm-btn-primary disabled:cursor-not-allowed disabled:opacity-50"
				>
					{submitting ? 'Saving…' : isEditMode ? 'Edit identity' : 'Identify disc'}
				</button>
			</div>
		</form>
	</div>
</div>
