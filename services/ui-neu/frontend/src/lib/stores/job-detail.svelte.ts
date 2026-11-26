// The job page's job: the loaded job detail, its loading and error state,
// the rendered naming preview and the values derived from the job alone.
import { goto } from '$app/navigation';
import { fetchJob, fetchNamingPreview, resolveJob, updateTrack } from '$lib/api/jobs';
import { ApiError } from '$lib/api/client';
import { errorMessage } from '$lib/utils/errors';
import type { JobDetailView, NamingPreviewItem } from '$lib/types/api.gen';
import type { EditableJobField } from '$lib/jobs/fields';
import { readJobMetadata } from '$lib/jobs/metadata';
import { buildResolveBody, cdEditBody, tvSeasonOrDiscChanged, type CdEdit } from '$lib/jobs/resolve';
import { isPostRipStatus } from '$lib/jobs/status-groups';
import { extractMusicTracks } from '$lib/music/tracks';
import { handSetTrackCount, isSeriesTrackList } from '$lib/jobs/track-fields';

// The last preview answered 409 (no routed session, so no template). The
// 5s poll then asks again only every PREVIEW_UNROUTED_EVERY_N_POLLS polls,
// so a route added elsewhere still shows up; explicit reloads always ask.
const PREVIEW_UNROUTED_EVERY_N_POLLS = 6;

// The job is gone (deleted, or an unknown id): the Backend answered 404.
function isNotFound(e: unknown): boolean {
	return e instanceof ApiError && e.status === 404;
}

export class JobDetail {
	detail = $state<JobDetailView | null>(null);
	loading = $state(true);
	error = $state<Error | null>(null);
	previewItems = $state<NamingPreviewItem[]>([]);
	// The last include/exclude toggle that failed: its track and why.
	excludeError = $state<{ trackId: string; message: string } | null>(null);
	#previewUnrouted = false;
	#previewSkippedPolls = 0;
	readonly #jobId: () => string;
	// eslint-disable-next-line svelte/prefer-svelte-reactivity -- plain Map, rebuilt by $derived whenever previewItems changes and never mutated
	previewByTrack = $derived(new Map(this.previewItems.map((i) => [i.track_id, i])));

	canResolve = $derived(!!this.detail && this.detail.job.actions.can_resolve);
	canApply = $derived(!!this.detail && this.detail.job.actions.can_apply);
	isVideoDisc = $derived(this.detail?.job.disc_type === 'dvd' || this.detail?.job.disc_type === 'bluray');
	isCdDisc = $derived(this.detail?.job.disc_type === 'cd');
	// A CD's scanned track count, so its track list has a row per track even
	// before any title is stored (0 without a scan or a job).
	cdTrackCount = $derived(this.detail ? (readJobMetadata(this.detail.job.metadata_json).titleCount ?? 0) : 0);
	musicTracks = $derived(
		this.detail
			? extractMusicTracks(this.detail.job.metadata_json, this.detail.job.disc_type === 'cd' ? this.cdTrackCount : 0)
			: []
	);
	tracksAreSeries = $derived(isSeriesTrackList(this.detail?.tracks ?? [], this.detail?.job.media_type));
	handSetCount = $derived(handSetTrackCount(this.detail?.tracks ?? []));
	// The loaded job's rip has finished (false until a job is loaded).
	isPostRip = $derived(this.detail ? isPostRipStatus(this.detail.job.status) : false);
	jobMeta = $derived(this.detail ? readJobMetadata(this.detail.job.metadata_json) : {});
	rawMetadataPairs = $derived(
		this.detail ? Object.entries((this.detail.job.metadata_json ?? {}) as Record<string, unknown>) : []
	);

	constructor(jobId: () => string) {
		this.#jobId = jobId;
	}

	setExcluded = async (trackId: string, excluded: boolean): Promise<void> => {
		this.excludeError = null;
		try {
			await updateTrack(this.#jobId(), trackId, { excluded });
		} catch (e) {
			this.excludeError = { trackId, message: errorMessage(e, 'Could not save') };
		} finally {
			// Refetch regardless: on success to pick up new naming/derived state,
			// on failure so the row can put the server's value back in its
			// checkbox once this resolves (JobTrackRow's toggleIncluded).
			await this.load();
		}
	};

	// A fact edited in place goes through resolve (see buildResolveBody). A TV
	// job's season or disc change re-runs the episode match, so this returns
	// true then and the caller restarts the match, which the panel shows as
	// matching until the run reports.
	saveFact = async (field: EditableJobField | 'title', raw: string): Promise<boolean> => {
		if (!this.detail) return false;
		const job = this.detail.job;
		// A CD's title is its album, kept in step with the music details.
		if (field === 'title' && job.disc_type === 'cd') {
			await this.saveCdField({ field: 'album' }, raw);
			return false;
		}
		const body = buildResolveBody(job, field, raw);
		const resp = await resolveJob(job.id, body);
		await this.load();
		return tvSeasonOrDiscChanged(job, resp?.job);
	};

	// A CD's artist, album or track title edited in place goes through resolve
	// with the stored music details restated around the one change. Saves run
	// one after another, each built from the job the previous one reloaded, so
	// a quick second edit cannot restate the first field's old value.
	#cdSaves: Promise<void> = Promise.resolve();
	saveCdField = (edit: CdEdit, raw: string): Promise<void> => {
		const run = this.#cdSaves.then(async () => {
			if (!this.detail) return;
			const job = this.detail.job;
			await resolveJob(job.id, cdEditBody(job, edit, raw, this.cdTrackCount));
			await this.load();
		});
		this.#cdSaves = run.catch(() => {});
		return run;
	};

	#loadPreview = async (id: string, poll: boolean): Promise<void> => {
		// Rendered filename preview is a best-effort SECOND fetch — never block
		// or fail the job render on it. Excluded tracks may be absent from items[].
		const skipPreview =
			poll && this.#previewUnrouted && ++this.#previewSkippedPolls % PREVIEW_UNROUTED_EVERY_N_POLLS !== 0;
		if (skipPreview) {
			return;
		}
		try {
			const preview = await fetchNamingPreview(id);
			this.previewItems = preview.items;
			this.#previewUnrouted = false;
		} catch (e) {
			this.previewItems = [];
			this.#previewUnrouted = e instanceof ApiError && e.status === 409;
			this.#previewSkippedPolls = 0;
		}
	};

	load = async ({ poll = false } = {}): Promise<void> => {
		const id = this.#jobId();
		// Only flip into the loading state on the FIRST load. The 5s poll
		// re-calls load() and on a slow network that would unmount the
		// rendered detail in favour of a skeleton, then remount when the
		// fetch settles. On refreshes we already have a previous payload to
		// render; just swap it in place when the new one arrives.
		const isInitialLoad = this.detail == null;
		if (isInitialLoad) {
			this.loading = true;
		}
		this.error = null;
		try {
			this.detail = await fetchJob(id);
			await this.#loadPreview(id, poll);
		} catch (e) {
			if (isNotFound(e)) {
				goto('/');
				return;
			}
			this.error = e instanceof Error ? e : new Error('Failed to load job');
		} finally {
			this.loading = false;
		}
	};
}
