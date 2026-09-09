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

	// Only the job's id matters here. The parent hands us a fresh `job` object
	// on every dashboard poll; depending on the object would re-run this and
	// flash "Resolving..." every tick.
	const jobId = $derived(job.id);

	$effect(() => {
		const sessionId = selected;
		const id = jobId;
		preview = null;
		previewProblem = null;
		previewToken = null;
		if (!sessionId) return;
		previewLoading = true;
		let cancelled = false;
		fetchNamingPreview(id, sessionId)
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

<div class="modal">
	<button
		type="button"
		class="apply-session-scrim"
		aria-label="Close dialog"
		onclick={onclose}
	></button>

	<div
		class="modal-panel modal-wide apply-session-panel"
		data-dialog
		role="dialog"
		aria-modal="true"
		aria-labelledby="apply-session-title"
	>
		<h3 id="apply-session-title" class="modal-title">
			Apply session to job
		</h3>

		{#if error}
			<p class="field-error apply-session-error" data-testid="apply-session-error">
				{error}
			</p>
		{/if}

		{#if collisions.length === 0}
			<label class="field apply-session-select-field">
				<span class="field-label">Session</span>
				<select
					id="apply-session-select"
					data-testid="apply-session-select"
					bind:value={selected}
				>
					<option value="" disabled>Choose...</option>
					{#each filteredSessions as s (s.id)}
						<option value={s.id}>{s.name} ({s.media_type})</option>
					{/each}
				</select>
			</label>

			{#if selectedSession}
				<div
					data-testid="recipe-preview"
					class="code-block apply-session-recipe"
				>
					<p class="apply-session-recipe-title">Recipe</p>
					<dl class="apply-session-recipe-list">
						<div class="apply-session-recipe-row">
							<dt class="apply-session-recipe-dt">Rip:</dt>
							<dd data-testid="recipe-rip-preset" class="apply-session-recipe-dd">
								{selectedRipPreset?.name ?? selectedSession.rip_preset_id}
							</dd>
						</div>
						<div class="apply-session-recipe-row">
							<dt class="apply-session-recipe-dt">Transcode:</dt>
							<dd
								data-testid="recipe-transcode-preset"
								class="apply-session-recipe-dd"
							>
								{selectedTranscodePreset?.name ?? 'No transcode'}
							</dd>
						</div>
						<div class="apply-session-recipe-row apply-session-recipe-row-col">
							<dt class="apply-session-recipe-dt">Output:</dt>
							<dd data-testid="recipe-output-path" class="apply-session-recipe-dd apply-session-recipe-output">
								{#if previewLoading}
									<span class="apply-session-recipe-faint">Resolving...</span>
								{:else if preview}
									<ul class="apply-session-recipe-output-list">
										{#each preview.items as item (item.track_id)}
											<li class="apply-session-recipe-output-item" title={item.output_path}>{item.output_path}</li>
										{/each}
									</ul>
									{#if preview.items.length === 0}
										<span class="apply-session-recipe-faint">No tracks to transcode with this session.</span>
									{/if}
								{/if}
							</dd>
						</div>
					</dl>
				</div>
				{#if previewProblem}
					<p
						data-testid="recipe-output-problem"
						class="apply-session-problem"
					>
						<svg class="apply-session-problem-icon" fill="none" stroke="currentColor" viewBox="0 0 24 24">
							<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-2.5L13.732 4c-.77-.833-1.964-.833-2.732 0L4.082 16.5c-.77.833.192 2.5 1.732 2.5z" />
						</svg>
						<span>{previewProblem}</span>
					</p>
				{/if}
			{/if}

			<div class="modal-actions">
				<button
					type="button"
					onclick={onclose}
					class="btn btn-ghost"
				>
					Cancel
				</button>
				<button
					type="button"
					data-testid="apply-session-apply"
					disabled={!selected || submitting || previewLoading || previewProblem !== null}
					onclick={() => applyOnce(false)}
					class="btn btn-primary"
				>
					{submitting ? 'Applying...' : 'Apply'}
				</button>
			</div>
		{:else}
			<p class="apply-session-collision-intro">
				This session can't be applied because of path collisions:
			</p>
			<ul class="apply-session-collision-list">
				{#each collisions as c (c.output_path + c.reason)}
					<li>
						<code class="mono apply-session-collision-path">{c.output_path}</code>
						<span class="apply-session-recipe-faint">({collisionLabel(c.reason)})</span>
					</li>
				{/each}
			</ul>

			{#if hasDuplicateInRequest}
				<p class="apply-session-collision-note">
					Two or more tracks resolve to the same output path - the session's template doesn't
					differentiate per track. Pick a session whose template includes <code>{'{track}'}</code>
					(e.g. <em>Movie -> Archive MKV</em>), or rip with a single-track preset.
					<strong>Overwrite</strong> won't help here.
				</p>
			{:else}
				<p class="apply-session-collision-note">
					Confirm <strong>Overwrite</strong> to queue anyway. The transcoder writes to
					<code>.arm-inprogress</code> first, so partial writes never replace the existing file.
				</p>
			{/if}

			<div class="modal-actions">
				<button
					type="button"
					onclick={onclose}
					class="btn btn-ghost"
				>
					Cancel
				</button>
				{#if !hasDuplicateInRequest}
					<button
						type="button"
						data-testid="apply-session-overwrite"
						disabled={submitting}
						onclick={() => applyOnce(true)}
						class="btn btn-danger"
					>
						{submitting ? 'Applying...' : 'Overwrite'}
					</button>
				{/if}
			</div>
		{/if}
	</div>
</div>

<style>
	/* .modal is display:flex/align/justify-center over the scrim - the
	   scrim button itself needs to fill that box and sit behind the panel
	   (same pattern ConfirmDialog.svelte uses: relative stacking context via
	   the panel's own z-index, no absolute/inset needed beyond covering the
	   modal's own padded box). */
	.apply-session-scrim { position: absolute; inset: 0; z-index: 0; background: transparent; border: 0; padding: 0; cursor: default; }
	.apply-session-panel { position: relative; z-index: 1; }
	.apply-session-error { margin-top: 0.5rem; }
	.apply-session-select-field { margin-top: 1rem; }
	/* original recipe box: rounded-lg border border-gray-200 bg-gray-50
	   px-3 py-2 text-sm - code-block's own font-mono/0.72rem sizing is for
	   literal preformatted text; this dl reads as prose, so type is reset
	   back to text-sm/text-secondary while keeping code-block's box (border,
	   radius, tint background). */
	.apply-session-recipe { margin-top: 0.75rem; font-family: var(--font-sans); font-size: 0.875rem; line-height: 1.25rem; white-space: normal; }
	.apply-session-recipe-title { font-weight: 500; color: var(--color-text-secondary); }
	.apply-session-recipe-list { margin-top: 0.25rem; display: flex; flex-direction: column; gap: 0.125rem; color: var(--color-text-muted); }
	.apply-session-recipe-row { display: flex; gap: 0.25rem; }
	.apply-session-recipe-row-col { flex-direction: column; }
	.apply-session-recipe-dt { flex-shrink: 0; }
	.apply-session-recipe-dd { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; color: var(--color-text); }
	.apply-session-recipe-output { font-family: var(--font-mono); font-size: 0.75rem; white-space: normal; }
	.apply-session-recipe-faint { color: var(--color-text-faint); }
	.apply-session-recipe-output-list { display: flex; flex-direction: column; gap: 0.125rem; }
	.apply-session-recipe-output-item { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
	.apply-session-problem { margin-top: 0.5rem; display: flex; align-items: flex-start; gap: 0.375rem; font-size: 0.875rem; color: var(--color-on-warning-soft); }
	.apply-session-problem-icon { flex-shrink: 0; margin-top: 0.125rem; width: 1rem; height: 1rem; }
	.apply-session-collision-intro { margin-top: 0.5rem; font-size: 0.875rem; color: var(--color-text-muted); }
	.apply-session-collision-list { margin-top: 0.5rem; display: flex; flex-direction: column; gap: 0.25rem; font-size: 0.875rem; }
	.apply-session-collision-path { color: var(--color-text); }
	.apply-session-collision-note { margin-top: 0.75rem; font-size: 0.875rem; color: var(--color-text-muted); }
</style>
