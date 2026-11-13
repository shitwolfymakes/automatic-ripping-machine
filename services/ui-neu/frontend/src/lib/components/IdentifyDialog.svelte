<script lang="ts">
	import { errorMessage } from '$lib/utils/errors';
	import { resolveJob } from '$lib/api/jobs';
	import type { JobView, ResolveResponse } from '$lib/types/api.gen';
	import TitleSearch from './TitleSearch.svelte';
	import IdentifyCdForm from './identify/IdentifyCdForm.svelte';
	import IdentifyVideoForm from './identify/IdentifyVideoForm.svelte';
	import { driveLabel } from '$lib/utils/drive-name';
	import { isAwaitingIdentity } from '$lib/utils/job-status-groups';
	import { readJobMetadata } from '$lib/utils/job-metadata';
	import { cdIdentifyBody, videoIdentifyBody } from '$lib/utils/job-resolve';

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
	const isEditMode = $derived(!isAwaitingIdentity(job.status));

	// CD-only: per-track count comes from the preserved scan_result on the
	// job's metadata_json. If it's absent we skip the per-track inputs and
	// show a helper line; the resolve still succeeds.
	const scanTrackCount = $derived(readJobMetadata(job.metadata_json).titleCount ?? 0);

	// Video / DVD / BD / data fields.
	let title = $state(job.title ?? '');
	let year = $state<number | null>(job.year);

	// CD fields.
	let album = $state(job.title ?? '');
	let artist = $state('');
	let trackTitles = $state<string[]>(Array.from({ length: scanTrackCount }, () => ''));

	let submitting = $state(false);
	let error = $state<string | null>(null);

	// A CD needs its album and artist; anything else needs a title.
	const cdFieldsFilled = $derived(album.trim().length > 0 && artist.trim().length > 0);
	const videoFieldsFilled = $derived(title.trim().length > 0);
	const canSubmit = $derived(!submitting && (isCd ? cdFieldsFilled : videoFieldsFilled));

	// A TV disc saved by hand has no show id, so episodes cannot be matched
	// automatically; the operator confirms that with a second click.
	const isEpisodic = $derived(!isCd && (job.looks_episodic || job.media_type === 'tv') && !job.has_series);
	let confirmNoMatch = $state(false);

	const submitLabel = $derived.by(() => {
		if (submitting) return 'Saving...';
		if (confirmNoMatch) return 'Save without a match';
		return isEditMode ? 'Edit identity' : 'Identify disc';
	});

	async function submit(event: Event): Promise<void> {
		event.preventDefault();
		if (!canSubmit) return;
		if (isEpisodic && !confirmNoMatch) {
			confirmNoMatch = true;
			return;
		}
		submitting = true;
		error = null;
		try {
			const body = isCd ? cdIdentifyBody({ album, artist, year, trackTitles }) : videoIdentifyBody({ title, year });
			const resp = await resolveJob(job.id, body);
			onidentified(resp);
		} catch (e) {
			error = errorMessage(e, 'Identify failed');
		} finally {
			submitting = false;
		}
	}
</script>

<div class="modal">
	<button type="button" class="identify-dialog-backdrop" aria-label="Close dialog" onclick={onclose}></button>

	<div class="modal-panel" data-dialog role="dialog" aria-modal="true" aria-labelledby="identify-dialog-title">
		<h3 id="identify-dialog-title" class="modal-title">
			{isEditMode ? 'Edit identity' : 'Identify this disc'}
		</h3>

		{#if error}
			<p class="field-error mt-2" data-testid="identify-error">
				{error}
			</p>
		{/if}

		{#if isEditMode}
			<p class="modal-body">
				Update the title, year, and metadata for this job. Status stays as-is. Existing transcoded files keep their
				original filenames - re-apply a session if you want new outputs under the corrected name.
			</p>
		{:else}
			<p class="modal-body">
				The disc on drive <code class="mono">{driveLabel(job.drive_id, driveNames)}</code> couldn't be identified automatically.
				Fill in the details so ARM can proceed. Any session you've already applied will pick up the resolved metadata and
				queue its transcode tasks.
			</p>
		{/if}

		{#if !isCd}
			<div class="mt-4 mb-3">
				<TitleSearch {job} onresolved={onidentified} />
			</div>
			<p class="field-help mt-4 mb-2">Or enter the title yourself</p>
		{/if}

		<form class={isCd ? 'mt-4' : 'mt-2'} onsubmit={submit}>
			{#if isCd}
				<IdentifyCdForm bind:album bind:year bind:artist bind:trackTitles {scanTrackCount} {submitting} />
			{:else}
				<IdentifyVideoForm bind:title bind:year {submitting} ontitleinput={() => (confirmNoMatch = false)} />
			{/if}

			{#if confirmNoMatch}
				<p class="field-help mb-2" data-testid="identify-no-match-warning">
					Without a search result ARM has no show id, so episodes can't be matched automatically.
				</p>
			{/if}

			<div class="modal-actions">
				<button type="button" onclick={onclose} disabled={submitting} class="btn"> Cancel </button>
				<button type="submit" disabled={!canSubmit} data-testid="identify-submit" class="btn btn-primary">
					{submitLabel}
				</button>
			</div>
		</form>
	</div>
</div>

<style>
	/* the backdrop click-catcher sits absolutely inside .modal (which already
	   draws the fixed scrim + centering); it just needs to fill that box */
	.identify-dialog-backdrop {
		position: absolute;
		inset: 0;
	}
</style>
