<script lang="ts">
	import { onMount } from 'svelte';
	import { fetchRipPresets, deleteRipPreset } from '$lib/api/ripPresets';
	import RipPresetForm from './RipPresetForm.svelte';
	import ConfirmDialog from './ConfirmDialog.svelte';
	import type {
		IdentificationMode,
		MediaType,
		OutputMode,
		RipPresetView,
		TrackSelection
	} from '$lib/types/api.gen';

	let presets = $state<RipPresetView[]>([]);
	let loading = $state(true);
	let error = $state<string | null>(null);

	// null = no form; 'new' = create form; otherwise the preset being edited.
	let editing = $state<RipPresetView | 'new' | null>(null);

	// Delete confirmation
	let deleteTarget = $state<RipPresetView | null>(null);

	async function load(): Promise<void> {
		loading = true;
		error = null;
		try {
			presets = await fetchRipPresets();
		} catch (e) {
			error = e instanceof Error ? e.message : 'Failed to load rip presets';
		} finally {
			loading = false;
		}
	}

	onMount(load);

	function startNew(): void {
		editing = 'new';
	}

	function startEdit(preset: RipPresetView): void {
		editing = preset;
	}

	async function handleSaved(): Promise<void> {
		editing = null;
		await load();
	}

	function handleCancel(): void {
		editing = null;
	}

	function requestDelete(preset: RipPresetView): void {
		deleteTarget = preset;
	}

	async function confirmDelete(): Promise<void> {
		const target = deleteTarget;
		deleteTarget = null;
		if (!target) return;
		try {
			await deleteRipPreset(target.id);
			// If the deleted preset was being edited, close the form.
			if (editing !== 'new' && editing?.id === target.id) editing = null;
			await load();
		} catch (e) {
			error = e instanceof Error ? e.message : 'Failed to delete preset';
		}
	}

	const MEDIA_TYPE_LABELS: Record<MediaType, string> = {
		movie: 'Movie',
		tv: 'TV',
		music: 'Music',
		data: 'Data',
		iso: 'ISO'
	};

	const TRACK_SELECTION_LABELS: Record<TrackSelection, string> = {
		main_feature: 'Main feature',
		all_tracks: 'All tracks',
		archive: 'Archive',
		custom: 'Custom'
	};

	const IDENTIFICATION_LABELS: Record<IdentificationMode, string> = {
		required: 'Required',
		skip: 'Skip',
		deferred_placeholder: 'Deferred placeholder'
	};

	const OUTPUT_LABELS: Record<OutputMode, string> = {
		tracks: 'Tracks',
		iso: 'ISO',
		data_copy: 'Data copy'
	};

	function label<T extends string>(map: Record<T, string>, value: T): string {
		return map[value] ?? value;
	}

	const cellClass = 'px-3 py-2 text-sm text-gray-700 dark:text-gray-300';
	const headClass =
		'px-3 py-2 text-left text-xs font-medium uppercase tracking-wider text-gray-500 dark:text-gray-400';
</script>

<section class="space-y-4">
	<div class="flex items-center justify-between">
		<div>
			<h2 class="text-lg font-semibold text-gray-900 dark:text-white">Rip Presets</h2>
			<p class="text-sm text-gray-500 dark:text-gray-400">
				Reusable disc-handling profiles that control track selection, identification, and output.
			</p>
		</div>
		<button
			type="button"
			onclick={startNew}
			data-testid="rip-preset-new"
			class="rounded-lg px-4 py-2 text-sm font-medium confirm-btn-primary"
		>
			New preset
		</button>
	</div>

	{#if error}
		<p class="text-sm text-red-600 dark:text-red-400" data-testid="rip-presets-error">{error}</p>
	{/if}

	{#if loading}
		<p class="py-8 text-center text-gray-400">Loading rip presets...</p>
	{:else if presets.length === 0}
		<p class="py-8 text-center text-gray-400">No rip presets yet.</p>
	{:else}
		<div class="overflow-x-auto rounded-lg border border-primary/10 bg-surface dark:bg-surface-dark dark:border-primary/10">
			<table class="min-w-full divide-y divide-primary/10 dark:divide-primary/10">
				<thead>
					<tr>
						<th class={headClass}>Name</th>
						<th class={headClass}>Media type</th>
						<th class={headClass}>Track selection</th>
						<th class={headClass}>Identification</th>
						<th class={headClass}>Output</th>
						<th class="{headClass} text-right">Actions</th>
					</tr>
				</thead>
				<tbody class="divide-y divide-primary/5 dark:divide-primary/5">
					{#each presets as preset (preset.id)}
						<tr data-testid="rip-preset-row">
							<td class={cellClass}>
								<span class="font-medium text-gray-900 dark:text-white">{preset.name}</span>
								{#if preset.is_builtin}
									<span
										class="ml-2 inline-flex items-center rounded-full bg-primary/10 px-2 py-0.5 text-xs font-medium text-primary-text dark:text-primary-text-dark"
										data-testid="rip-preset-builtin-badge"
									>
										Built-in
									</span>
								{/if}
							</td>
							<td class={cellClass}>{label(MEDIA_TYPE_LABELS, preset.media_type)}</td>
							<td class={cellClass}>{label(TRACK_SELECTION_LABELS, preset.track_selection)}</td>
							<td class={cellClass}>{label(IDENTIFICATION_LABELS, preset.identification_mode)}</td>
							<td class={cellClass}>{label(OUTPUT_LABELS, preset.output_mode)}</td>
							<td class="{cellClass} text-right">
								<div class="flex justify-end gap-2">
									<button
										type="button"
										onclick={() => startEdit(preset)}
										data-testid="rip-preset-edit"
										class="rounded-lg border border-primary/20 px-3 py-1.5 text-xs font-medium text-primary-text transition-colors hover:bg-primary/10 dark:border-primary/20 dark:text-primary-text-dark dark:hover:bg-primary/15"
									>
										Edit
									</button>
									{#if !preset.is_builtin}
										<button
											type="button"
											onclick={() => requestDelete(preset)}
											data-testid="rip-preset-delete"
											class="rounded-lg border border-red-300 px-3 py-1.5 text-xs font-medium text-red-700 transition-colors hover:bg-red-50 dark:border-red-700 dark:text-red-400 dark:hover:bg-red-900/20"
										>
											Delete
										</button>
									{/if}
								</div>
							</td>
						</tr>
					{/each}
				</tbody>
			</table>
		</div>
	{/if}

	{#if editing !== null}
		<div class="rounded-lg border border-primary/15 bg-surface p-4 dark:bg-surface-dark dark:border-primary/15" data-testid="rip-preset-form">
			<RipPresetForm
				preset={editing === 'new' ? null : editing}
				onsaved={handleSaved}
				oncancel={handleCancel}
			/>
		</div>
	{/if}
</section>

<ConfirmDialog
	open={deleteTarget !== null}
	title="Delete rip preset"
	message={deleteTarget ? `Delete the rip preset "${deleteTarget.name}"? This cannot be undone.` : ''}
	confirmLabel="Delete"
	variant="danger"
	onconfirm={confirmDelete}
	oncancel={() => (deleteTarget = null)}
/>
