// One live-progress store keyed by job id.
//
// A surface calls `jobLive.watch(job)` (in an $effect, so it re-runs when the
// job's status changes) and reads `jobLive.get(job.id)`. Every topic is
// reference-counted, so overlapping surfaces never drop each other's feed.
//
// Rip: follows ripper.progress.{job} while a watched job is ripping.
// Transcode: follows transcode.progress.{task} for each in-progress task of a
// watched job (found from the dashboard store's active_transcodes rows) and for
// every task passed to followTask.
import { wsClient } from '$lib/api/ws';
import { dashboard } from '$lib/stores/dashboard';
import type { JobView, TranscodeTaskView } from '$lib/types/api.gen';
import { createRipFeed, estimateEtaSeconds, transcodeSample, type LiveSample } from '$lib/live/feeds';

export interface TaskLive extends LiveSample {
	taskId: string;
}

export interface JobLive {
	rip: LiveSample | null;
	transcode: TaskLive | null;
}

/** For tests and skeletons: nothing live. */
export const EMPTY_LIVE: JobLive = { rip: null, transcode: null };

type Payload = Record<string, unknown>;
type RipFeed = ReturnType<typeof createRipFeed>;
type TopicHandler = Parameters<typeof wsClient.subscribe>[1];

class RefCountedTopics {
	#held = new Map<string, { count: number; off: () => void }>();

	acquire(topic: string, handler: TopicHandler): void {
		const held = this.#held.get(topic);
		if (held) held.count++;
		else this.#held.set(topic, { count: 1, off: wsClient.subscribe(topic, handler) });
	}

	/** Drop one hold; true when that was the last one and the topic closed. */
	release(topic: string): boolean {
		const held = this.#held.get(topic);
		if (!held || --held.count > 0) return false;
		held.off();
		this.#held.delete(topic);
		return true;
	}
}

/** A task row as a sample; its ETA falls back to an estimate from started_at. */
function rowSample(row: TranscodeTaskView): LiveSample {
	return {
		pct: row.progress_pct,
		etaSeconds: row.eta_seconds ?? estimateEtaSeconds(row.started_at, row.progress_pct, Date.now()),
		fps: row.fps ?? null,
		avgFps: row.avg_fps ?? null,
		pass: row.current_pass ?? null,
		bytesDone: null,
		bytesTotal: null,
		rateBps: null,
		phase: null,
		trackId: null
	};
}

/** Live fields win when non-null; the row fills the rest. */
function mergeSamples(live: LiveSample, fallback: LiveSample): LiveSample {
	const reported = Object.entries(live).filter(([, value]) => value !== null);
	return { ...fallback, ...Object.fromEntries(reported) };
}

function mergeTask(taskId: string, live: LiveSample | undefined, row: TranscodeTaskView | null | undefined) {
	if (!row) return live ? { ...live, taskId } : null;
	return { ...(live ? mergeSamples(live, rowSample(row)) : rowSample(row)), taskId };
}

export class JobLiveStore {
	#rip = $state<Record<string, LiveSample>>({});
	#samples = $state<Record<string, LiveSample>>({});
	#rows = $state<TranscodeTaskView[]>([]);

	#topics = new RefCountedTopics();
	// eslint-disable-next-line svelte/prefer-svelte-reactivity -- bookkeeping, never rendered
	#ripFeeds = new Map<string, RipFeed>();
	/** watched job id -> watcher count */
	// eslint-disable-next-line svelte/prefer-svelte-reactivity -- bookkeeping, never rendered
	#watchedJobs = new Map<string, number>();
	/** task ids held on behalf of watched jobs */
	// eslint-disable-next-line svelte/prefer-svelte-reactivity -- bookkeeping, never rendered
	#heldTasks = new Set<string>();
	#offDashboard: (() => void) | null = null;

	/** Follow a job's live progress; returns the unwatch. */
	watch = (job: Pick<JobView, 'id' | 'status'>): (() => void) => {
		this.#ensureDashboard();
		this.#watchedJobs.set(job.id, (this.#watchedJobs.get(job.id) ?? 0) + 1);
		const ripping = job.status === 'ripping';
		if (ripping) this.#acquireRip(job.id);
		this.#reconcileTasks();
		return () => {
			if (ripping) this.#releaseRip(job.id);
			this.#unwatchJob(job.id);
		};
	};

	/** Follow one transcode task by id (TranscodeCard); returns the unfollow. */
	followTask = (taskId: string): (() => void) => {
		this.#ensureDashboard();
		this.#acquireTask(taskId);
		return () => this.#releaseTask(taskId);
	};

	/** The live record for a job; reactive. */
	get = (jobId: string): JobLive => {
		return { rip: this.#rip[jobId] ?? null, transcode: this.#transcodeFor(jobId) };
	};

	/** One task's live record merged over its row (when given); reactive. */
	task = (taskId: string, row?: TranscodeTaskView | null): TaskLive | null => {
		return mergeTask(taskId, this.#samples[taskId], row);
	};

	#transcodeFor(jobId: string): TaskLive | null {
		const row = this.#rows.find((t) => t.job_id === jobId && t.status === 'in_progress');
		return row ? this.task(row.id, row) : null;
	}

	#acquireRip(jobId: string): void {
		const topic = `ripper.progress.${jobId}`;
		let feed = this.#ripFeeds.get(jobId);
		if (!feed) {
			feed = createRipFeed();
			this.#ripFeeds.set(jobId, feed);
		}
		const ownFeed = feed;
		this.#topics.acquire(topic, (env) => this.#onRip(jobId, ownFeed, env.payload));
	}

	#releaseRip(jobId: string): void {
		if (!this.#topics.release(`ripper.progress.${jobId}`)) return;
		this.#ripFeeds.delete(jobId);
		this.#rip = Object.fromEntries(Object.entries(this.#rip).filter(([id]) => id !== jobId));
	}

	#onRip(jobId: string, feed: RipFeed, payload: Payload): void {
		this.#rip = { ...this.#rip, [jobId]: feed(payload, Date.now()) };
	}

	#acquireTask(taskId: string): void {
		this.#topics.acquire(`transcode.progress.${taskId}`, (env) => {
			this.#samples = { ...this.#samples, [taskId]: transcodeSample(env.payload) };
		});
	}

	#releaseTask(taskId: string): void {
		if (!this.#topics.release(`transcode.progress.${taskId}`)) return;
		this.#samples = Object.fromEntries(Object.entries(this.#samples).filter(([id]) => id !== taskId));
	}

	#unwatchJob(jobId: string): void {
		const remaining = (this.#watchedJobs.get(jobId) ?? 1) - 1;
		if (remaining > 0) {
			this.#watchedJobs.set(jobId, remaining);
			return;
		}
		this.#watchedJobs.delete(jobId);
		this.#reconcileTasks();
	}

	#ensureDashboard(): void {
		if (this.#offDashboard) return;
		this.#offDashboard = dashboard.subscribe((d) => {
			this.#rows = d.active_transcodes ?? [];
			this.#reconcileTasks();
		});
	}

	/** Hold exactly the task topics for watched jobs' in-progress tasks. */
	#reconcileTasks(): void {
		// eslint-disable-next-line svelte/prefer-svelte-reactivity -- local lookup, never stored
		const wanted = new Set(
			this.#rows
				.filter((t) => t.status === 'in_progress' && t.job_id && this.#watchedJobs.has(t.job_id))
				.map((t) => t.id)
		);
		for (const id of [...this.#heldTasks].filter((held) => !wanted.has(held))) {
			this.#releaseTask(id);
			this.#heldTasks.delete(id);
		}
		for (const id of [...wanted].filter((w) => !this.#heldTasks.has(w))) {
			this.#acquireTask(id);
			this.#heldTasks.add(id);
		}
	}
}

export const jobLive = new JobLiveStore();
