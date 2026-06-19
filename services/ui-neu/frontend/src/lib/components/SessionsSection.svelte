<script lang="ts">
	import { onMount } from 'svelte';
	import { fetchSessions, deleteSession, cloneSession } from '$lib/api/sessions';
	import { fetchRipPresets } from '$lib/api/ripPresets';
	import { fetchTranscodePresets } from '$lib/api/transcodePresets';
	import SessionForm from './SessionForm.svelte';
	import ConfirmDialog from './ConfirmDialog.svelte';
	import type { MediaType, SessionView } from '$lib/types/api.gen';

	let sessions = $state<SessionView[]>([]);
	let ripNames = $state<Map<string, string>>(new Map());
	let transcodeNames = $state<Map<string, string>>(new Map());
	let loading = $state(true);
	let error = $state<string | null>(null);

	// null = no form; 'new' = create form; otherwise the session being edited.
	let editing = $state<SessionView | 'new' | null>(null);
	let deleteTarget = $state<SessionView | null>(null);

	// Clone inline box.
	let cloneTarget = $state<SessionView | null>(null);
	let cloneName = $state('');

	async function load(): Promise<void> {
		loading = true;
		error = null;
		try {
			const [rows, rips, tcs] = await Promise.all([
				fetchSessions(),
				fetchRipPresets(),
				fetchTranscodePresets()
			]);
			sessions = rows;
			ripNames = new Map(rips.map((p) => [p.id, p.name]));
			transcodeNames = new Map(tcs.map((p) => [p.id, p.name]));
		} catch (e) {
			error = e instanceof Error ? e.message : 'Failed to load sessions';
		} finally {
			loading = false;
		}
	}

	onMount(load);

	function startNew(): void {
		cloneTarget = null;
		editing = 'new';
	}

	function startEdit(s: SessionView): void {
		cloneTarget = null;
		editing = s;
	}

	async function handleSaved(): Promise<void> {
		editing = null;
		await load();
	}

	function handleCancel(): void {
		editing = null;
	}

	function startClone(s: SessionView): void {
		editing = null;
		cloneTarget = s;
		cloneName = `${s.name} (copy)`;
	}

	async function submitClone(): Promise<void> {
		const target = cloneTarget;
		if (!target || !cloneName.trim()) return;
		try {
			await cloneSession(target.id, { name: cloneName });
			cloneTarget = null;
			await load();
		} catch (e) {
			error = e instanceof Error ? e.message : 'Clone failed';
		}
	}

	function requestDelete(s: SessionView): void {
		deleteTarget = s;
	}

	async function confirmDelete(): Promise<void> {
		const target = deleteTarget;
		deleteTarget = null;
		if (!target) return;
		try {
			await deleteSession(target.id);
			if (editing !== 'new' && editing?.id === target.id) editing = null;
			await load();
		} catch (e) {
			error = e instanceof Error ? e.message : 'Failed to delete session';
		}
	}

	const MEDIA_TYPE_LABELS: Record<MediaType, string> = {
		movie: 'Movie',
		tv: 'TV',
		music: 'Music',
		data: 'Data',
		iso: 'ISO'
	};

	function mediaLabel(v: MediaType): string {
		return MEDIA_TYPE_LABELS[v] ?? v;
	}
	function ripLabel(id: string): string {
		return ripNames.get(id) ?? id;
	}
	function transcodeLabel(id: string | null | undefined): string {
		if (!id) return '- none -';
		return transcodeNames.get(id) ?? id;
	}

	const cellClass = 'px-3 py-2 text-sm text-gray-700 dark:text-gray-300';
	const headClass =
		'px-3 py-2 text-left text-xs font-medium uppercase tracking-wider text-gray-500 dark:text-gray-400';
</script>

<section class="space-y-4">
	<div class="flex items-center justify-between">
		<div>
			<h2 class="text-lg font-semibold text-gray-900 dark:text-white">Sessions</h2>
			<p class="text-sm text-gray-500 dark:text-gray-400">
				Reusable recipes binding a rip preset, an optional transcode preset, and an output-path
				template.
			</p>
		</div>
		<button
			type="button"
			onclick={startNew}
			data-testid="session-new"
			class="rounded-lg px-4 py-2 text-sm font-medium confirm-btn-primary"
		>
			New session
		</button>
	</div>

	{#if error}
		<p class="text-sm text-red-600 dark:text-red-400" data-testid="sessions-error">{error}</p>
	{/if}

	{#if loading}
		<p class="py-8 text-center text-gray-400">Loading sessions...</p>
	{:else if sessions.length === 0}
		<p class="py-8 text-center text-gray-400">No sessions yet.</p>
	{:else}
		<div class="overflow-x-auto rounded-lg border border-primary/10 bg-surface dark:bg-surface-dark dark:border-primary/10">
			<table class="min-w-full divide-y divide-primary/10 dark:divide-primary/10">
				<thead>
					<tr>
						<th class={headClass}>Name</th>
						<th class={headClass}>Media</th>
						<th class={headClass}>Rip preset</th>
						<th class={headClass}>Transcode preset</th>
						<th class={headClass}>Output template</th>
						<th class="{headClass} text-right">Actions</th>
					</tr>
				</thead>
				<tbody class="divide-y divide-primary/5 dark:divide-primary/5">
					{#each sessions as s (s.id)}
						<tr data-testid="session-row">
							<td class={cellClass}>
								<span class="font-medium text-gray-900 dark:text-white">{s.name}</span>
								{#if s.is_builtin}
									<span
										class="ml-2 inline-flex items-center rounded-full bg-primary/10 px-2 py-0.5 text-xs font-medium text-primary-text dark:text-primary-text-dark"
										data-testid="session-builtin-badge"
									>
										Built-in
									</span>
								{/if}
							</td>
							<td class={cellClass}>{mediaLabel(s.media_type)}</td>
							<td class={cellClass}>{ripLabel(s.rip_preset_id)}</td>
							<td class={cellClass}>{transcodeLabel(s.transcode_preset_id)}</td>
							<td class={cellClass}>
								<code class="rounded bg-primary/5 px-1.5 py-0.5 text-xs text-primary-text dark:text-primary-text-dark">{s.output_path_template}</code>
							</td>
							<td class="{cellClass} text-right">
								<div class="flex justify-end gap-2">
									<button
										type="button"
										onclick={() => startEdit(s)}
										data-testid="session-edit"
										class="rounded-lg border border-primary/20 px-3 py-1.5 text-xs font-medium text-primary-text transition-colors hover:bg-primary/10 dark:border-primary/20 dark:text-primary-text-dark dark:hover:bg-primary/15"
									>
										Edit
									</button>
									<button
										type="button"
										onclick={() => startClone(s)}
										data-testid="session-clone"
										class="rounded-lg border border-primary/20 px-3 py-1.5 text-xs font-medium text-primary-text transition-colors hover:bg-primary/10 dark:border-primary/20 dark:text-primary-text-dark dark:hover:bg-primary/15"
									>
										Clone
									</button>
									{#if !s.is_builtin}
										<button
											type="button"
											onclick={() => requestDelete(s)}
											data-testid="session-delete"
											class="rounded-lg border border-red-300 px-3 py-1.5 text-xs font-medium text-red-700 transition-colors hover:bg-red-50 dark:border-red-700 dark:text-red-400 dark:hover:bg-red-900/20"
										>
											Delete
										</button>
									{/if}
								</div>
							</td>
						</tr>
						{#if editing !== 'new' && editing?.id === s.id}
							<tr data-testid="session-edit-row">
								<td colspan="6" class="p-4 bg-primary/5 dark:bg-primary/10">
									<div data-testid="session-form">
										<SessionForm session={editing} onsaved={handleSaved} oncancel={handleCancel} />
									</div>
								</td>
							</tr>
						{/if}
					{/each}
				</tbody>
			</table>
		</div>
	{/if}

	{#if cloneTarget !== null}
		<div class="rounded-lg border border-primary/15 bg-surface p-4 dark:bg-surface-dark dark:border-primary/15" data-testid="session-clone-box">
			<h3 class="mb-2 text-base font-semibold text-gray-900 dark:text-white">Clone "{cloneTarget.name}"</h3>
			<label class="text-sm font-medium text-gray-700 dark:text-gray-300" for="session-clone-name">New name</label>
			<input
				id="session-clone-name"
				data-testid="session-clone-name"
				type="text"
				bind:value={cloneName}
				class="mt-1 w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 dark:border-gray-600 dark:bg-gray-800 dark:text-white"
			/>
			<div class="mt-3 flex justify-end gap-3">
				<button
					type="button"
					onclick={() => (cloneTarget = null)}
					class="rounded-lg px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-100 dark:text-gray-300 dark:hover:bg-gray-700"
				>
					Cancel
				</button>
				<button
					type="button"
					onclick={submitClone}
					disabled={!cloneName.trim()}
					data-testid="session-clone-submit"
					class="rounded-lg px-4 py-2 text-sm font-medium confirm-btn-primary disabled:cursor-not-allowed disabled:opacity-50"
				>
					Create clone
				</button>
			</div>
		</div>
	{/if}

	{#if editing === 'new'}
		<div class="rounded-lg border border-primary/15 bg-surface p-4 dark:bg-surface-dark dark:border-primary/15" data-testid="session-form">
			<SessionForm session={null} onsaved={handleSaved} oncancel={handleCancel} />
		</div>
	{/if}
</section>

<ConfirmDialog
	open={deleteTarget !== null}
	title="Delete session"
	message={deleteTarget ? `Delete the session "${deleteTarget.name}"? This cannot be undone.` : ''}
	confirmLabel="Delete"
	variant="danger"
	onconfirm={confirmDelete}
	oncancel={() => (deleteTarget = null)}
/>
