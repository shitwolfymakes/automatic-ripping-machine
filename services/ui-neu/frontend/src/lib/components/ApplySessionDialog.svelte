<script lang="ts">
	import { onMount } from 'svelte';
	import { fetchSessions } from '$lib/api/sessions';
	import { fetchRipPresets } from '$lib/api/ripPresets';
	import { fetchTranscodePresets } from '$lib/api/transcodePresets';
	import { applySession, fetchNamingPreview } from '$lib/api/jobs';
	import { ApiError } from '$lib/api/client';
	import type {
		ApplySessionResponse,
		CollisionInfo,
		DiscType,
		JobNamingPreviewResponse,
		JobView,
		MediaType,
		RipPresetView,
		SessionView,
		TranscodePresetView
	} from '$lib/types/api.gen';

	let {
		job,
		onclose,
		onapplied
	}: {
		job: JobView;
		onclose: () => void;
		onapplied: (resp: ApplySessionResponse) => void;
	} = $props();

	let sessions = $state<SessionView[]>([]);
	let ripPresets = $state<RipPresetView[]>([]);
	let transcodePresets = $state<TranscodePresetView[]>([]);
	let selected = $state<string>('');
	let collisions = $state<CollisionInfo[]>([]);
	let error = $state<string | null>(null);
	let submitting = $state(false);

	// Faithful port of Vue's discTypeToMediaType: dvd/bluray → movie, cd → music,
	// data → data, otherwise (e.g. unknown) → null (show all).
	function discTypeToMediaType(dt: DiscType): MediaType | null {
		if (dt === 'dvd' || dt === 'bluray') return 'movie';
		if (dt === 'cd') return 'music';
		if (dt === 'data') return 'data';
		return null;
	}

	const filteredSessions = $derived.by(() => {
		const mt = discTypeToMediaType(job.disc_type);
		return sessions.filter((s) => mt === null || s.media_type === mt || s.media_type === 'tv');
	});

	const hasDuplicateInRequest = $derived(
		collisions.some((c) => c.reason === 'duplicate_in_request')
	);

	function collisionLabel(reason: CollisionInfo['reason']): string {
		if (reason === 'existing_task') return 'queued/done in DB';
		if (reason === 'on_disk') return 'exists on disk';
		return 'duplicate within this apply';
	}

	const selectedSession = $derived(sessions.find((s) => s.id === selected) ?? null);

	const ripById = $derived(new Map(ripPresets.map((p) => [p.id, p])));
	const tcById = $derived(new Map(transcodePresets.map((p) => [p.id, p])));

	const selectedRipPreset = $derived(
		selectedSession ? (ripById.get(selectedSession.rip_preset_id) ?? null) : null
	);
	const selectedTranscodePreset = $derived(
		selectedSession && selectedSession.transcode_preset_id
			? (tcById.get(selectedSession.transcode_preset_id) ?? null)
			: null
	);
	// Real output paths for THIS job with the chosen session, from the same
	// resolver the apply path uses. A missing token (e.g. the job has no year)
	// comes back as a 422 naming it; explain it and block Apply, since apply
	// would fail the same way.
	let preview = $state<JobNamingPreviewResponse | null>(null);
	let previewLoading = $state(false);
	let previewProblem = $state<string | null>(null);
	let previewToken = $state<string | null>(null);

	const TOKEN_WORDS: Record<string, string> = {
		title: 'a title',
		year: 'a year',
		show: 'a show name',
		season: 'a season',
		episode: 'an episode number',
		episode_title: 'an episode title',
		artist: 'an artist',
		album: 'an album',
		disc: 'a disc number',
		track_title: 'track titles',
		transcode_slug: 'a transcode preset',
		ext: 'a transcode preset'
	};

	function explainProblem(message: string): void {
		const m = /token \{(\w+)\}/.exec(message);
		previewToken = m ? m[1] : null;
		if (previewToken === 'transcode_slug' || previewToken === 'ext') {
			previewProblem = `This session has no transcode preset, so {${previewToken}} in its output path cannot be filled. Give the session a transcode preset or choose another session.`;
		} else if (previewToken) {
			const what = (TOKEN_WORDS[previewToken] ?? `a value for {${previewToken}}`).replace(/^an? /, '');
			previewProblem = `This job has no ${what}, so {${previewToken}} in the output path cannot be filled. Add it in the job's details, or choose a session whose output path does not use {${previewToken}}.`;
		} else {
			previewProblem = message;
		}
	}

	$effect(() => {
		const sessionId = selected;
		preview = null;
		previewProblem = null;
		previewToken = null;
		if (!sessionId) return;
		previewLoading = true;
		let cancelled = false;
		fetchNamingPreview(job.id, sessionId)
			.then((p) => {
				if (!cancelled) preview = p;
			})
			.catch((e) => {
				if (cancelled) return;
				explainProblem(e instanceof Error ? e.message : 'Preview failed');
			})
			.finally(() => {
				if (!cancelled) previewLoading = false;
			});
		return () => {
			cancelled = true;
		};
	});

	onMount(async () => {
		// Sessions drive the picker; the rip/transcode preset lists only enrich the
		// recipe preview. Fetch them independently so a preset-list failure degrades
		// the preview (names fall back to ids) rather than breaking the dialog.
		try {
			sessions = await fetchSessions();
		} catch {
			sessions = [];
		}
		try {
			[ripPresets, transcodePresets] = await Promise.all([
				fetchRipPresets(),
				fetchTranscodePresets()
			]);
		} catch {
			ripPresets = [];
			transcodePresets = [];
		}
	});

	async function applyOnce(overwrite: boolean): Promise<void> {
		submitting = true;
		error = null;
		try {
			const resp = await applySession(job.id, { session_id: selected, overwrite });
			onapplied(resp);
		} catch (e) {
			if (e instanceof ApiError && e.status === 409 && e.body && typeof e.body === 'object') {
				const detail = (e.body as { detail?: { collisions?: CollisionInfo[] } }).detail;
				if (detail?.collisions) {
					collisions = detail.collisions;
					return;
				}
			}
			error = e instanceof Error ? e.message : 'Apply failed';
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
		class="relative z-10 w-full max-w-md rounded-lg bg-surface p-6 shadow-xl dark:bg-surface-dark"
		data-dialog
		role="dialog"
		aria-modal="true"
		aria-labelledby="apply-session-title"
	>
		<h3 id="apply-session-title" class="text-lg font-semibold text-gray-900 dark:text-white">
			Apply session to job
		</h3>

		{#if error}
			<p class="mt-2 text-sm text-red-600 dark:text-red-400" data-testid="apply-session-error">
				{error}
			</p>
		{/if}

		{#if collisions.length === 0}
			<div class="mt-4">
				<label
					for="apply-session-select"
					class="block text-sm font-medium text-gray-700 dark:text-gray-300"
				>
					Session
				</label>
				<select
					id="apply-session-select"
					data-testid="apply-session-select"
					bind:value={selected}
					class="mt-1 w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 dark:border-gray-600 dark:bg-gray-800 dark:text-white"
				>
					<option value="" disabled>Choose...</option>
					{#each filteredSessions as s (s.id)}
						<option value={s.id}>{s.name} ({s.media_type})</option>
					{/each}
				</select>
			</div>

			{#if selectedSession}
				<div
					data-testid="recipe-preview"
					class="mt-3 rounded-lg border border-gray-200 bg-gray-50 px-3 py-2 text-sm dark:border-gray-700 dark:bg-gray-800/60"
				>
					<p class="font-medium text-gray-700 dark:text-gray-300">Recipe</p>
					<dl class="mt-1 space-y-0.5 text-gray-600 dark:text-gray-400">
						<div class="flex gap-1">
							<dt class="shrink-0">Rip:</dt>
							<dd data-testid="recipe-rip-preset" class="truncate text-gray-900 dark:text-gray-100">
								{selectedRipPreset?.name ?? selectedSession.rip_preset_id}
							</dd>
						</div>
						<div class="flex gap-1">
							<dt class="shrink-0">Transcode:</dt>
							<dd
								data-testid="recipe-transcode-preset"
								class="truncate text-gray-900 dark:text-gray-100"
							>
								{selectedTranscodePreset?.name ?? 'No transcode'}
							</dd>
						</div>
						<div class="flex flex-col gap-1">
							<dt class="shrink-0">Output:</dt>
							<dd data-testid="recipe-output-path" class="font-mono text-xs text-gray-900 dark:text-gray-100">
								{#if previewLoading}
									<span class="text-gray-400">Resolving...</span>
								{:else if preview}
									<ul class="space-y-0.5">
										{#each preview.items as item (item.track_id)}
											<li class="truncate" title={item.output_path}>{item.output_path}</li>
										{/each}
									</ul>
									{#if preview.items.length === 0}
										<span class="text-gray-400">No tracks to transcode with this session.</span>
									{/if}
								{/if}
							</dd>
						</div>
					</dl>
				</div>
				{#if previewProblem}
					<p
						data-testid="recipe-output-problem"
						class="mt-2 flex items-start gap-1.5 text-sm text-amber-700 dark:text-amber-400"
					>
						<svg class="mt-0.5 h-4 w-4 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
							<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-2.5L13.732 4c-.77-.833-1.964-.833-2.732 0L4.082 16.5c-.77.833.192 2.5 1.732 2.5z" />
						</svg>
						<span>{previewProblem}</span>
					</p>
				{/if}
			{/if}

			<div class="mt-4 flex justify-end gap-3">
				<button
					type="button"
					onclick={onclose}
					class="rounded-lg px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-100 dark:text-gray-300 dark:hover:bg-gray-700"
				>
					Cancel
				</button>
				<button
					type="button"
					data-testid="apply-session-apply"
					disabled={!selected || submitting || previewLoading || previewProblem !== null}
					onclick={() => applyOnce(false)}
					class="confirm-btn-primary rounded-lg px-4 py-2 text-sm font-medium disabled:cursor-not-allowed disabled:opacity-50"
				>
					{submitting ? 'Applying...' : 'Apply'}
				</button>
			</div>
		{:else}
			<p class="mt-2 text-sm text-gray-600 dark:text-gray-400">
				This session can't be applied because of path collisions:
			</p>
			<ul class="mt-2 space-y-1 text-sm">
				{#each collisions as c (c.output_path + c.reason)}
					<li>
						<code class="text-gray-900 dark:text-gray-100">{c.output_path}</code>
						<span class="text-gray-500 dark:text-gray-400">({collisionLabel(c.reason)})</span>
					</li>
				{/each}
			</ul>

			{#if hasDuplicateInRequest}
				<p class="mt-3 text-sm text-gray-500 dark:text-gray-400">
					Two or more tracks resolve to the same output path - the session's template doesn't
					differentiate per track. Pick a session whose template includes <code>{'{track}'}</code>
					(e.g. <em>Movie -> Archive MKV</em>), or rip with a single-track preset.
					<strong>Overwrite</strong> won't help here.
				</p>
			{:else}
				<p class="mt-3 text-sm text-gray-500 dark:text-gray-400">
					Confirm <strong>Overwrite</strong> to queue anyway. The transcoder writes to
					<code>.arm-inprogress</code> first, so partial writes never replace the existing file.
				</p>
			{/if}

			<div class="mt-4 flex justify-end gap-3">
				<button
					type="button"
					onclick={onclose}
					class="rounded-lg px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-100 dark:text-gray-300 dark:hover:bg-gray-700"
				>
					Cancel
				</button>
				{#if !hasDuplicateInRequest}
					<button
						type="button"
						data-testid="apply-session-overwrite"
						disabled={submitting}
						onclick={() => applyOnce(true)}
						class="confirm-btn-danger rounded-lg px-4 py-2 text-sm font-medium disabled:cursor-not-allowed disabled:opacity-50"
					>
						{submitting ? 'Applying...' : 'Overwrite'}
					</button>
				{/if}
			</div>
		{/if}
	</div>
</div>
