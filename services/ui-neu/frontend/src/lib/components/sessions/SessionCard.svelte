<script lang="ts">
	import type { JoinedSession } from './sessionsData.svelte';
	import { resolveSample } from './sampleTokens';

	interface Props {
		session: JoinedSession;
		onedit: () => void;
		onclone: () => void;
		ondelete: () => void;
	}

	let { session, onedit, onclone, ondelete }: Props = $props();

	// Humanise enum values for display
	function humanizeTrackSelection(v: string | null | undefined): string {
		switch (v) {
			case 'main_feature': return 'Main feature';
			case 'all_tracks': return 'All tracks';
			case 'archive': return 'Archive';
			case 'custom': return 'Custom';
			default: return v ?? '—';
		}
	}

	function humanizeOutputMode(v: string | null | undefined): string {
		switch (v) {
			case 'tracks': return 'Tracks';
			case 'iso': return 'ISO image';
			case 'data_copy': return 'File copy';
			default: return v ?? '—';
		}
	}

	function humanizeMediaType(v: string | null | undefined): string {
		switch (v) {
			case 'movie': return 'Movie';
			case 'tv': return 'TV';
			case 'music': return 'Music';
			case 'data': return 'Data';
			case 'iso': return 'ISO';
			default: return v ?? '—';
		}
	}

	let ripSummary = $derived(
		session.ripPreset
			? `${humanizeTrackSelection(session.ripPreset.track_selection)} · ${humanizeOutputMode(session.ripPreset.output_mode)}`
			: '—'
	);

	let transcodeSummary = $derived(
		session.transcodePreset
			? `${session.transcodePreset.container} · ${session.transcodePreset.codec ?? '—'} · ${session.transcodePreset.hw_preference ?? ''}`
			: null
	);

	let samplePath = $derived(
		resolveSample(session.output_path_template, session.media_type)
	);

	const MEDIA_PILL: Record<string, string> = {
		movie: 'bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-300',
		tv: 'bg-purple-100 text-purple-700 dark:bg-purple-900/30 dark:text-purple-300',
		music: 'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-300',
		data: 'bg-gray-100 text-gray-700 dark:bg-gray-700/30 dark:text-gray-300',
		iso: 'bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-300',
	};

	let pillClass = $derived(MEDIA_PILL[session.media_type] ?? 'bg-gray-100 text-gray-700');
</script>

<div class="rounded-lg border border-primary/20 bg-surface shadow-xs dark:bg-surface-dark px-4 py-3">
	<div class="flex flex-wrap items-start gap-x-4 gap-y-2">
		<!-- Media type pill -->
		<span class="inline-block shrink-0 rounded px-2 py-0.5 text-xs font-semibold uppercase tracking-wide {pillClass}">
			{humanizeMediaType(session.media_type)}
		</span>

		<!-- Name + BUILT-IN badge -->
		<div class="flex min-w-0 flex-1 items-center gap-2">
			<span class="truncate font-semibold text-sm text-gray-900 dark:text-white">
				{session.name}
			</span>
			{#if session.is_builtin}
				<span
					class="shrink-0 rounded px-1.5 py-0.5 text-xs font-bold tracking-widest bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-300"
					title="Built-in sessions cannot be deleted; clone to customise"
				>
					BUILT-IN
				</span>
			{/if}
		</div>

		<!-- Action buttons -->
		<div class="flex shrink-0 items-center gap-1.5">
			<button
				onclick={onedit}
				class="rounded-md border border-primary/30 bg-primary/10 px-3 py-1 text-xs font-medium text-primary hover:bg-primary/20"
			>{session.is_builtin ? 'View' : 'Edit'}</button>
			<button
				onclick={onclone}
				class="rounded-md border border-gray-300 px-3 py-1 text-xs font-medium text-gray-600 hover:bg-gray-50 dark:border-gray-600 dark:text-gray-300 dark:hover:bg-gray-800"
			>Clone</button>
			<button
				onclick={ondelete}
				disabled={session.is_builtin}
				class="rounded-md border border-red-300 px-3 py-1 text-xs font-medium text-red-600 hover:bg-red-50 disabled:cursor-not-allowed disabled:opacity-40 dark:border-red-700 dark:text-red-400 dark:hover:bg-red-900/20"
			>Delete</button>
		</div>
	</div>

	<!-- Recipe container: rip → transcode → output, each area divided -->
	<div class="mt-3 grid grid-cols-1 divide-y divide-primary/15 rounded-md border border-primary/15 bg-black/10 text-xs sm:grid-cols-[1fr_auto_1fr_auto_1fr] sm:divide-x sm:divide-y-0 dark:bg-black/20">
		<!-- Rip preset -->
		<div class="flex flex-col gap-0.5 px-4 py-3">
			<span class="font-medium uppercase tracking-wide text-gray-400 dark:text-gray-500">Rip preset</span>
			<span class="font-medium text-gray-800 dark:text-gray-200">
				{session.ripPreset?.name ?? session.rip_preset_id}
			</span>
			<span class="text-gray-500 dark:text-gray-400">{ripSummary}</span>
		</div>

		<!-- Arrow -->
		<div class="hidden items-center justify-center px-1 text-lg font-semibold text-gray-400 dark:text-gray-600 sm:flex" aria-hidden="true">&gt;</div>

		<!-- Transcode preset -->
		<div class="flex flex-col gap-0.5 px-4 py-3">
			<span class="font-medium uppercase tracking-wide text-gray-400 dark:text-gray-500">Transcode</span>
			{#if session.transcodePreset}
				<span class="font-medium text-gray-800 dark:text-gray-200">
					{session.transcodePreset.name}
				</span>
				<span class="text-gray-500 dark:text-gray-400">{transcodeSummary}</span>
			{:else}
				<span class="italic text-gray-400 dark:text-gray-500">No transcode</span>
			{/if}
		</div>

		<!-- Arrow -->
		<div class="hidden items-center justify-center px-1 text-lg font-semibold text-gray-400 dark:text-gray-600 sm:flex" aria-hidden="true">&gt;</div>

		<!-- Output path sample -->
		<div class="flex flex-col gap-0.5 px-4 py-3">
			<span class="font-medium uppercase tracking-wide text-gray-400 dark:text-gray-500">Output path</span>
			<span class="break-all font-mono text-gray-700 dark:text-gray-300">{samplePath}</span>
		</div>
	</div>
</div>
