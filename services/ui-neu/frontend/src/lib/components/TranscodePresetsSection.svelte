<script lang="ts">
	import { onMount } from 'svelte';
	import { fetchTranscodePresets, deleteTranscodePreset } from '$lib/api/transcodePresets';
	import TranscodePresetForm from './TranscodePresetForm.svelte';
	import ConfirmDialog from './ConfirmDialog.svelte';
	import type {
		ContainerFormat,
		HwPreference,
		MediaType,
		TranscodePresetView,
		TranscodeTool
	} from '$lib/types/api.gen';

	let presets = $state<TranscodePresetView[]>([]);
	let loading = $state(true);
	let error = $state<string | null>(null);

	// null = no form; 'new' = create form; otherwise the preset being edited.
	let editing = $state<TranscodePresetView | 'new' | null>(null);
	let deleteTarget = $state<TranscodePresetView | null>(null);

	async function load(): Promise<void> {
		loading = true;
		error = null;
		try {
			presets = await fetchTranscodePresets();
		} catch (e) {
			error = e instanceof Error ? e.message : 'Failed to load transcode presets';
		} finally {
			loading = false;
		}
	}

	onMount(load);

	function startNew(): void {
		editing = 'new';
	}

	function startEdit(preset: TranscodePresetView): void {
		editing = preset;
	}

	async function handleSaved(): Promise<void> {
		editing = null;
		await load();
	}

	function handleCancel(): void {
		editing = null;
	}

	function requestDelete(preset: TranscodePresetView): void {
		deleteTarget = preset;
	}

	async function confirmDelete(): Promise<void> {
		const target = deleteTarget;
		deleteTarget = null;
		if (!target) return;
		try {
			await deleteTranscodePreset(target.id);
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

	const TOOL_LABELS: Record<TranscodeTool, string> = {
		handbrake: 'HandBrake',
		abcde: 'abcde',
		none: 'None'
	};

	const CONTAINER_LABELS: Record<ContainerFormat, string> = {
		mkv: 'MKV',
		mp4: 'MP4',
		webm: 'WebM',
		flac: 'FLAC',
		mp3: 'MP3',
		ogg: 'OGG',
		iso: 'ISO',
		none: 'None'
	};

	const HW_LABELS: Record<HwPreference, string> = {
		cpu_only: 'CPU only',
		any: 'Any'
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
			<h2 class="text-lg font-semibold text-gray-900 dark:text-white">Transcode Presets</h2>
			<p class="text-sm text-gray-500 dark:text-gray-400">
				Reusable encoding profiles that control the transcode tool, container, codec, and hardware.
			</p>
		</div>
		<button
			type="button"
			onclick={startNew}
			data-testid="transcode-preset-new"
			class="rounded-lg px-4 py-2 text-sm font-medium confirm-btn-primary"
		>
			New preset
		</button>
	</div>

	{#if error}
		<p class="text-sm text-red-600 dark:text-red-400" data-testid="transcode-presets-error">{error}</p>
	{/if}

	{#if loading}
		<p class="py-8 text-center text-gray-400">Loading transcode presets...</p>
	{:else if presets.length === 0}
		<p class="py-8 text-center text-gray-400">No transcode presets yet.</p>
	{:else}
		<div class="overflow-x-auto rounded-lg border border-primary/10 bg-surface dark:bg-surface-dark dark:border-primary/10">
			<table class="min-w-full divide-y divide-primary/10 dark:divide-primary/10">
				<thead>
					<tr>
						<th class={headClass}>Name</th>
						<th class={headClass}>Media type</th>
						<th class={headClass}>Tool</th>
						<th class={headClass}>Container</th>
						<th class={headClass}>HW preference</th>
						<th class="{headClass} text-right">Actions</th>
					</tr>
				</thead>
				<tbody class="divide-y divide-primary/5 dark:divide-primary/5">
					{#each presets as preset (preset.id)}
						<tr data-testid="transcode-preset-row">
							<td class={cellClass}>
								<span class="font-medium text-gray-900 dark:text-white">{preset.name}</span>
								{#if preset.is_builtin}
									<span
										class="ml-2 inline-flex items-center rounded-full bg-primary/10 px-2 py-0.5 text-xs font-medium text-primary-text dark:text-primary-text-dark"
										data-testid="transcode-preset-builtin-badge"
									>
										Built-in
									</span>
								{/if}
							</td>
							<td class={cellClass}>{label(MEDIA_TYPE_LABELS, preset.media_type)}</td>
							<td class={cellClass}>{label(TOOL_LABELS, preset.tool)}</td>
							<td class={cellClass}>{label(CONTAINER_LABELS, preset.container)}</td>
							<td class={cellClass}>
								{preset.hw_preference ? label(HW_LABELS, preset.hw_preference) : '-'}
							</td>
							<td class="{cellClass} text-right">
								<div class="flex justify-end gap-2">
									<button
										type="button"
										onclick={() => startEdit(preset)}
										data-testid="transcode-preset-edit"
										class="rounded-lg border border-primary/20 px-3 py-1.5 text-xs font-medium text-primary-text transition-colors hover:bg-primary/10 dark:border-primary/20 dark:text-primary-text-dark dark:hover:bg-primary/15"
									>
										Edit
									</button>
									{#if !preset.is_builtin}
										<button
											type="button"
											onclick={() => requestDelete(preset)}
											data-testid="transcode-preset-delete"
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
		<div class="rounded-lg border border-primary/15 bg-surface p-4 dark:bg-surface-dark dark:border-primary/15" data-testid="transcode-preset-form">
			<TranscodePresetForm
				preset={editing === 'new' ? null : editing}
				onsaved={handleSaved}
				oncancel={handleCancel}
			/>
		</div>
	{/if}
</section>

<ConfirmDialog
	open={deleteTarget !== null}
	title="Delete transcode preset"
	message={deleteTarget ? `Delete the transcode preset "${deleteTarget.name}"? This cannot be undone.` : ''}
	confirmLabel="Delete"
	variant="danger"
	onconfirm={confirmDelete}
	oncancel={() => (deleteTarget = null)}
/>
