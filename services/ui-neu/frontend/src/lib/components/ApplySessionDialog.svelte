<script lang="ts">
	import { errorMessage } from '$lib/utils/errors';
	import { onMount } from 'svelte';
	import { fetchSessions } from '$lib/api/sessions';
	import { fetchRipPresets } from '$lib/api/ripPresets';
	import { fetchTranscodePresets } from '$lib/api/transcodePresets';
	import { applySession } from '$lib/api/jobs';
	import { transcodeRuntimeEnabled } from '$lib/stores/config';
	import { NamingPreview } from '$lib/stores/namingPreview.svelte';
	import ApplySessionCollisions from './apply-session/ApplySessionCollisions.svelte';
	import ApplySessionRecipe from './apply-session/ApplySessionRecipe.svelte';
	import { collisionsFromApplyError } from '$lib/utils/apply-collisions';
	import { isPassthroughSession, presetToolMap, sessionsForDisc } from '$lib/utils/sessions';
	import type {
		ApplySessionResponse,
		CollisionInfo,
		JobView,
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
	// Only meaningful for the runtime-disabled passthrough filter below: true
	// until the concurrent sessions+presets fetch in onMount settles, so that
	// branch can tell "presets not loaded yet" apart from "no passthrough
	// sessions exist".
	let presetsLoading = $state(true);
	let selected = $state<string>('');
	let collisions = $state<CollisionInfo[]>([]);
	let error = $state<string | null>(null);
	let submitting = $state(false);

	// id -> tool for the passthrough filter below; presetToolById.get(id) is
	// undefined until transcodePresets has loaded, which only excludes
	// preset-backed sessions from the filtered list until then (a session
	// with no preset at all is unaffected).
	const presetToolById = $derived(presetToolMap(transcodePresets));

	const filteredSessions = $derived.by(() => {
		const byMediaType = sessionsForDisc(sessions, job.disc_type);
		// Encode sessions can only be applied while transcoding is running;
		// when it's disabled, only passthrough-compatible sessions are offered
		// - but only once transcodePresets has loaded (presetsLoading), since a
		// preset-backed session's passthrough status is unknown until then and
		// the dialog shows a loading affordance instead of this list meanwhile.
		if (!$transcodeRuntimeEnabled && !presetsLoading) {
			return byMediaType.filter((s) => isPassthroughSession(s, presetToolById));
		}
		return byMediaType;
	});

	const selectedSession = $derived(sessions.find((s) => s.id === selected) ?? null);

	// The real output paths for this job with the chosen session. A missing
	// token (for example, the job has no year) comes back as a 422 naming it,
	// and the dialog explains it and blocks Apply, since apply would fail the
	// same way.
	const namingPreview = new NamingPreview();

	// Only the job's id matters here. The parent hands us a fresh `job` object
	// on every dashboard poll; depending on the object would re-run this and
	// flash "Resolving..." every tick.
	const jobId = $derived(job.id);

	$effect(() => namingPreview.load(jobId, selected));

	onMount(() => {
		// Sessions drive the picker; the rip/transcode preset lists enrich the
		// recipe preview and (when transcoding is runtime-disabled) gate the
		// passthrough filter on filteredSessions. Fire both fetches
		// CONCURRENTLY (not sessions-then-presets) and let each update its own
		// state independently as it settles - sessions no longer waits on a
		// sequential presets round-trip, and a preset-list failure still only
		// degrades the recipe preview (names fall back to ids) rather than
		// breaking the dialog.
		fetchSessions()
			.then((s) => {
				sessions = s;
			})
			.catch(() => {
				sessions = [];
			});
		Promise.all([fetchRipPresets(), fetchTranscodePresets()])
			.then(([rp, tp]) => {
				ripPresets = rp;
				transcodePresets = tp;
			})
			.catch(() => {
				ripPresets = [];
				transcodePresets = [];
			})
			.finally(() => {
				presetsLoading = false;
			});
	});

	async function applyOnce(overwrite: boolean): Promise<void> {
		submitting = true;
		error = null;
		try {
			const resp = await applySession(job.id, { session_id: selected, overwrite });
			onapplied(resp);
		} catch (e) {
			const found = collisionsFromApplyError(e);
			if (found) {
				collisions = found;
				return;
			}
			error = errorMessage(e, 'Apply failed');
		} finally {
			submitting = false;
		}
	}
</script>

<div class="modal">
	<button type="button" class="apply-session-scrim" aria-label="Close dialog" onclick={onclose}></button>

	<div
		class="modal-panel modal-wide apply-session-panel"
		data-dialog
		role="dialog"
		aria-modal="true"
		aria-labelledby="apply-session-title"
	>
		<h3 id="apply-session-title" class="modal-title">Apply session to job</h3>

		{#if error}
			<p class="field-error apply-session-error" data-testid="apply-session-error">
				{error}
			</p>
		{/if}

		{#if collisions.length === 0}
			<label class="field apply-session-select-field">
				<span class="field-label">Session</span>
				{#if !$transcodeRuntimeEnabled && presetsLoading}
					<!-- The passthrough filter needs preset tool data to know which
					     preset-backed sessions qualify; show a loading affordance
					     instead of a list that would otherwise render empty and be
					     indistinguishable from "no passthrough sessions". -->
					<p class="field-help" data-testid="apply-session-presets-loading">Loading...</p>
				{:else}
					<select id="apply-session-select" data-testid="apply-session-select" bind:value={selected}>
						<option value="" disabled>Choose...</option>
						{#each filteredSessions as s (s.id)}
							<option value={s.id}>{s.name} ({s.media_type})</option>
						{/each}
					</select>
				{/if}
			</label>

			{#if !$transcodeRuntimeEnabled && !presetsLoading}
				<p class="field-help" data-testid="apply-session-passthrough-hint">
					Transcoding is disabled; only passthrough sessions are listed.
				</p>
			{/if}

			{#if selectedSession}
				<ApplySessionRecipe
					session={selectedSession}
					{ripPresets}
					{transcodePresets}
					preview={namingPreview.preview}
					loading={namingPreview.loading}
					problem={namingPreview.problem}
				/>
			{/if}

			<div class="modal-actions">
				<button type="button" onclick={onclose} class="btn btn-ghost"> Cancel </button>
				<button
					type="button"
					data-testid="apply-session-apply"
					disabled={!selected || submitting || namingPreview.loading || namingPreview.problem !== null}
					onclick={() => applyOnce(false)}
					class="btn btn-primary"
				>
					{submitting ? 'Applying...' : 'Apply'}
				</button>
			</div>
		{:else}
			<ApplySessionCollisions {collisions} jobId={job.id} {submitting} {onclose} onoverwrite={() => applyOnce(true)} />
		{/if}
	</div>
</div>

<style>
	/* .modal is display:flex/align/justify-center over the scrim - the
	   scrim button itself needs to fill that box and sit behind the panel
	   (same pattern ConfirmDialog.svelte uses: relative stacking context via
	   the panel's own z-index, no absolute/inset needed beyond covering the
	   modal's own padded box). */
	.apply-session-scrim {
		position: absolute;
		inset: 0;
		z-index: 0;
		background: transparent;
		border: 0;
		padding: 0;
		cursor: default;
	}
	.apply-session-panel {
		position: relative;
		z-index: 1;
	}
	.apply-session-error {
		margin-top: 0.5rem;
	}
	.apply-session-select-field {
		margin-top: 1rem;
	}
</style>
