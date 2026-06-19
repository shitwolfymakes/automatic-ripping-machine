<script lang="ts">
	import { onMount } from 'svelte';
	import { fetchSessions } from '$lib/api/sessions';
	import { applySession } from '$lib/api/jobs';
	import { ApiError } from '$lib/api/client';
	import type {
		ApplySessionResponse,
		CollisionInfo,
		DiscType,
		JobView,
		MediaType,
		SessionView
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

	onMount(async () => {
		sessions = await fetchSessions();
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
					disabled={!selected || submitting}
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
