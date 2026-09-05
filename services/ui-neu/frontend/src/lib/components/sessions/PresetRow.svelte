<script lang="ts">
	import type { RipPresetView, TranscodePresetView } from '$lib/types/api.gen';

	type RipKind = { kind: 'rip'; preset: RipPresetView };
	type TranscodeKind = { kind: 'transcode'; preset: TranscodePresetView };

	interface Props {
		kind: 'rip' | 'transcode';
		preset: RipPresetView | TranscodePresetView;
		usedBy: number;
		onview: () => void;
		onedit: () => void;
		onclone: () => void;
		ondelete: () => void;
	}

	let { kind, preset, usedBy, onview, onedit, onclone, ondelete }: Props = $props();

	// ── Humanise helpers ─────────────────────────────────────────────────────

	function humanizeMediaType(v: string | null | undefined): string {
		switch (v) {
			case 'movie': return 'Movie';
			case 'tv': return 'TV';
			case 'music': return 'Music';
			case 'data': return 'Data';
			case 'iso': return 'ISO';
			default: return v ?? '-';
		}
	}

	function humanizeTrackSelection(v: string | null | undefined): string {
		switch (v) {
			case 'main_feature': return 'Main feature';
			case 'all_tracks': return 'All tracks';
			case 'archive': return 'Archive';
			case 'custom': return 'Custom';
			default: return v ?? '-';
		}
	}

	function humanizeIdentificationMode(v: string | null | undefined): string {
		switch (v) {
			case 'required': return 'ID required';
			case 'skip': return 'ID skip';
			case 'deferred_placeholder': return 'ID deferred';
			default: return v ?? '-';
		}
	}

	function humanizeOutputMode(v: string | null | undefined): string {
		switch (v) {
			case 'tracks': return 'Tracks';
			case 'iso': return 'ISO image';
			case 'data_copy': return 'File copy';
			default: return v ?? '-';
		}
	}

	function humanizeTool(v: string | null | undefined): string {
		switch (v) {
			case 'handbrake': return 'HandBrake';
			case 'abcde': return 'abcde';
			case 'none': return 'None';
			default: return v ?? '-';
		}
	}

	function humanizeContainer(v: string | null | undefined): string {
		switch (v) {
			case 'mkv': return 'MKV';
			case 'mp4': return 'MP4';
			case 'webm': return 'WebM';
			case 'flac': return 'FLAC';
			case 'mp3': return 'MP3';
			case 'ogg': return 'OGG';
			case 'iso': return 'ISO';
			case 'none': return 'None';
			default: return v ?? '-';
		}
	}

	function humanizeCodec(v: string | null | undefined): string {
		switch (v) {
			case 'h264': return 'H.264';
			case 'h265': return 'H.265';
			case 'av1': return 'AV1';
			default: return v ?? '-';
		}
	}

	function humanizeHw(v: string | null | undefined): string {
		switch (v) {
			case 'cpu_only': return 'CPU only';
			case 'any': return 'Any (HW)';
			default: return v ?? '-';
		}
	}

	// ── Derived values ────────────────────────────────────────────────────────

	let summary = $derived(
		kind === 'rip'
			? (() => {
				const p = preset as RipPresetView;
				return `${humanizeTrackSelection(p.track_selection)} · ${humanizeIdentificationMode(p.identification_mode)} · ${humanizeOutputMode(p.output_mode)}`;
			})()
			: (() => {
				const p = preset as TranscodePresetView;
				return `${humanizeTool(p.tool)} · ${humanizeContainer(p.container)} · ${p.codec ? humanizeCodec(p.codec) : '-'} · ${humanizeHw(p.hw_preference)}`;
			})()
	);

	let deleteDisabled = $derived(preset.is_builtin || usedBy > 0);

	let deleteTitle = $derived(
		preset.is_builtin
			? 'Built-in preset: clone to edit or remove'
			: usedBy > 0
				? `Used by ${usedBy} session(s): repoint them first`
				: undefined
	);

	// ── Media pill ────────────────────────────────────────────────────────────

	const MEDIA_PILL: Record<string, string> = {
		movie: 'bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-300',
		tv: 'bg-purple-100 text-purple-700 dark:bg-purple-900/30 dark:text-purple-300',
		music: 'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-300',
		data: 'bg-gray-100 text-gray-700 dark:bg-gray-700/30 dark:text-gray-300',
		iso: 'bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-300',
	};

	let pillClass = $derived(MEDIA_PILL[preset.media_type] ?? 'bg-gray-100 text-gray-700');
</script>

<div class="rounded-lg border border-primary/20 bg-surface shadow-xs dark:bg-surface-dark px-4 py-3">
	<div class="flex flex-wrap items-start gap-x-4 gap-y-2">
		<!-- Media type pill -->
		<span class="inline-block shrink-0 rounded px-2 py-0.5 text-xs font-semibold uppercase tracking-wide {pillClass}">
			{humanizeMediaType(preset.media_type)}
		</span>

		<!-- Name + BUILT-IN badge -->
		<div class="flex min-w-0 flex-1 items-center gap-2">
			<span class="truncate font-semibold text-sm text-gray-900 dark:text-white">
				{preset.name}
			</span>
			{#if preset.is_builtin}
				<span
					class="shrink-0 rounded px-1.5 py-0.5 text-xs font-bold tracking-widest bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-300"
					title="Built-in presets cannot be deleted; clone to customise"
				>
					BUILT-IN
				</span>
			{/if}
		</div>

		<!-- Action buttons -->
		<div class="flex shrink-0 items-center gap-1.5">
			<!-- Built-ins are read-only: "View" opens a locked form; custom: "Edit" -->
			<button
				onclick={preset.is_builtin ? onview : onedit}
				class="rounded-md border border-primary/30 bg-primary/10 px-3 py-1 text-xs font-medium text-primary hover:bg-primary/20"
			>{preset.is_builtin ? 'View' : 'Edit'}</button>

			<button
				onclick={onclone}
				class="rounded-md border border-gray-300 px-3 py-1 text-xs font-medium text-gray-600 hover:bg-gray-50 dark:border-gray-600 dark:text-gray-300 dark:hover:bg-gray-800"
			>Clone</button>

			<button
				onclick={ondelete}
				disabled={deleteDisabled}
				title={deleteTitle}
				class="rounded-md border border-red-300 px-3 py-1 text-xs font-medium text-red-600 hover:bg-red-50 disabled:cursor-not-allowed disabled:opacity-40 dark:border-red-700 dark:text-red-400 dark:hover:bg-red-900/20"
			>Delete</button>
		</div>
	</div>

	<!-- ID + summary row -->
	<div class="mt-2 flex flex-wrap items-center gap-x-4 gap-y-1 text-xs">
		<!-- ID -->
		<code class="rounded bg-gray-100 px-1.5 py-0.5 font-mono text-gray-600 dark:bg-gray-800 dark:text-gray-400">
			{preset.id}
		</code>

		<!-- One-line summary -->
		<span class="text-gray-500 dark:text-gray-400">{summary}</span>

		<!-- Used by chip -->
		<span class="inline-block rounded-full border border-gray-300 px-2.5 py-0.5 text-xs font-medium text-gray-600 dark:border-gray-600 dark:text-gray-400">
			Used by {usedBy}
		</span>
	</div>
</div>
