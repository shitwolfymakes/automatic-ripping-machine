// The job page's job: the loaded job detail, its loading and error state,
// the rendered naming preview and the values derived from the job alone.
import { goto } from '$app/navigation';
import { fetchJob, fetchNamingPreview, resolveJob, updateTrack } from '$lib/api/jobs';
import { ApiError } from '$lib/api/client';
import type { JobDetailView, NamingPreviewItem } from '$lib/types/api.gen';
import type { EditableJobField } from '$lib/jobs/fields';
import { readJobMetadata } from '$lib/jobs/metadata';
import { buildResolveBody, tvSeasonOrDiscChanged } from '$lib/jobs/resolve';
import { isPostRipStatus } from '$lib/jobs/status-groups';
import { extractMusicTracks } from '$lib/music/tracks';
import { handSetTrackCount, isSeriesTrackList } from '$lib/jobs/track-fields';

// The last preview answered 409 (no routed session, so no template). The
// 5s poll then asks again only every PREVIEW_UNROUTED_EVERY_N_POLLS polls,
// so a route added elsewhere still shows up; explicit reloads always ask.
const PREVIEW_UNROUTED_EVERY_N_POLLS = 6;

// The check reads the error message for '404'; #536 covers it.
function isNotFound(e: unknown): boolean {
	return e instanceof Error && e.message.includes('404');
}

export class JobDetail {
	detail = $state<JobDetailView | null>(null);
	loading = $state(true);
	error = $state<Error | null>(null);
	previewItems = $state<NamingPreviewItem[]>([]);
	#previewUnrouted = false;
	#previewSkippedPolls = 0;
	readonly #jobId: () => string;
	// eslint-disable-next-line svelte/prefer-svelte-reactivity -- plain Map, rebuilt by $derived whenever previewItems changes and never mutated
	previewByTrack = $derived(new Map(this.previewItems.map((i) => [i.track_id, i])));

	canResolve = $derived(!!this.detail && this.detail.job.actions.can_resolve);
	canApply = $derived(!!this.detail && this.detail.job.actions.can_apply);
	isVideoDisc = $derived(this.detail?.job.disc_type === 'dvd' || this.detail?.job.disc_type === 'bluray');
	isCdDisc = $derived(this.detail?.job.disc_type === 'cd');
	musicTracks = $derived(this.detail ? extractMusicTracks(this.detail.job.metadata_json) : []);
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
		try {
			await updateTrack(this.#jobId(), trackId, { excluded });
		} finally {
			// Refetch regardless: on success to pick up new naming/derived state,
			// on failure to restore the last server-truth value in the checkbox.
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
		const body = buildResolveBody(job, field, raw);
		const resp = await resolveJob(job.id, body);
		await this.load();
		return tvSeasonOrDiscChanged(job, resp?.job);
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
