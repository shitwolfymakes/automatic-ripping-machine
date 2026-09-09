<script lang="ts">
	import { resolveJob } from '$lib/api/jobs';
	import type { JobView, ResolveResponse } from '$lib/types/api.gen';
	import { driveLabel } from '$lib/utils/drive-name';

	let {
		job,
		driveNames,
		onclose,
		onidentified
	}: {
		job: JobView;
		driveNames?: Record<string, string> | null;
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

<div class="modal">
	<button
		type="button"
		class="identify-dialog-backdrop"
		aria-label="Close dialog"
		onclick={onclose}
	></button>

	<div
		class="modal-panel"
		data-dialog
		role="dialog"
		aria-modal="true"
		aria-labelledby="identify-dialog-title"
	>
		<h3
			id="identify-dialog-title"
			class="modal-title"
		>
			{isEditMode ? 'Edit identity' : 'Identify this disc'}
		</h3>

		{#if error}
			<p class="field-error mt-2" data-testid="identify-error">
				{error}
			</p>
		{/if}

		{#if isEditMode}
			<p class="modal-body">
				Update the title, year, and metadata for this job. Status stays as-is. Existing
				transcoded files keep their original filenames - re-apply a session if you want new
				outputs under the corrected name.
			</p>
		{:else}
			<p class="modal-body">
				The disc on drive <code class="mono">{driveLabel(job.drive_id, driveNames)}</code> couldn't be identified
				automatically. Fill in the details so ARM can proceed. Any session you've already applied
				will pick up the resolved metadata and queue its transcode tasks.
			</p>
		{/if}

		<form class="mt-4" onsubmit={submit}>
			{#if isCd}
				<div class="mb-3 flex gap-3">
					<label class="field identify-dialog-field-wide">
						<span class="field-label">Album</span>
						<input
							bind:value={album}
							type="text"
							required
							data-testid="identify-album"
							disabled={submitting}
						/>
					</label>
					<label class="field flex-1">
						<span class="field-label">Year</span>
						<input
							bind:value={year}
							type="number"
							min="1888"
							max="2100"
							data-testid="identify-year"
							disabled={submitting}
						/>
					</label>
				</div>
				<div class="mb-3">
					<label class="field">
						<span class="field-label">Artist</span>
						<input
							bind:value={artist}
							type="text"
							required
							data-testid="identify-artist"
							disabled={submitting}
						/>
					</label>
				</div>
				{#if scanTrackCount > 0}
					<div class="mb-3">
						<div class="field-label mb-1">Track titles</div>
						{#each trackTitles as _t, idx (idx)}
							<div class="mb-1 flex items-center gap-2">
								<span class="w-8 identify-dialog-track-index">
									{String(idx + 1).padStart(2, '0')}
								</span>
								<input
									bind:value={trackTitles[idx]}
									type="text"
									data-testid={`identify-track-${idx + 1}`}
									disabled={submitting}
									class="field-control flex-1"
								/>
							</div>
						{/each}
					</div>
				{:else}
					<p class="field-help mb-3">
						Track count couldn't be determined from the scan; transcoded filenames will fall back
						to generic names.
					</p>
				{/if}
			{:else}
				<div class="mb-3 flex gap-3">
					<label class="field identify-dialog-field-wide">
						<span class="field-label">Title</span>
						<input
							bind:value={title}
							type="text"
							required
							data-testid="identify-title"
							disabled={submitting}
						/>
					</label>
					<label class="field flex-1">
						<span class="field-label">Year</span>
						<input
							bind:value={year}
							type="number"
							min="1888"
							max="2100"
							data-testid="identify-year"
							disabled={submitting}
						/>
					</label>
				</div>
			{/if}

			<div class="modal-actions">
				<button
					type="button"
					onclick={onclose}
					disabled={submitting}
					class="btn"
				>
					Cancel
				</button>
				<button
					type="submit"
					disabled={!canSubmit}
					data-testid="identify-submit"
					class="btn btn-primary"
				>
					{submitting ? 'Saving...' : isEditMode ? 'Edit identity' : 'Identify disc'}
				</button>
			</div>
		</form>
	</div>
</div>

<style>
	.identify-dialog-track-index { text-align: right; font-size: 0.875rem; line-height: 1.25rem; color: var(--color-text-muted); }
	/* the backdrop click-catcher sits absolutely inside .modal (which already
	   draws the fixed scrim + centering); it just needs to fill that box */
	.identify-dialog-backdrop { position: absolute; inset: 0; }
	.identify-dialog-field-wide { flex: 2 1 0%; }
</style>
