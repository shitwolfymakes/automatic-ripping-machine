<script lang="ts">
	import type { MediaType } from '$lib/types/api.gen';
	import { previewTemplate } from '$lib/api/sessions';

	interface Props {
		value: string;
		mediaType: MediaType;
		onchange: (v: string) => void;
		has_transcode_preset?: boolean;
		id?: string;
		disabled?: boolean;
	}

	let { value, mediaType, onchange, has_transcode_preset, id, disabled = false }: Props = $props();

	// Valid tokens per media type
	const TOKENS: Record<MediaType, string[]> = {
		movie: ['title', 'year', 'track', 'duration_human', 'transcode_slug', 'ext'],
		tv: ['show', 'year', 'season', 'disc', 'track', 'episode', 'episode_title', 'duration_human', 'transcode_slug', 'ext'],
		music: ['artist', 'album', 'disc', 'track', 'track_title', 'transcode_slug', 'ext'],
		data: ['title'],
		iso: ['title', 'year', 'ext'],
	};

	let expansion = $state<string | null>(null);
	let previewError = $state<string | null>(null);
	// Non-reactive — just a handle for clearTimeout; must NOT be $state (would cause effect cycles)
	let debounceTimer: ReturnType<typeof setTimeout> | null = null;

	$effect(() => {
		// Access reactive values to track them
		const template = value;
		const type = mediaType;

		if (debounceTimer !== null) {
			clearTimeout(debounceTimer);
		}

		if (!template) {
			expansion = null;
			previewError = null;
			return;
		}

		debounceTimer = setTimeout(async () => {
			try {
				const body: { template: string; media_type: MediaType; has_transcode_preset?: boolean } = {
					template,
					media_type: type,
				};
				if (has_transcode_preset !== undefined) {
					body.has_transcode_preset = has_transcode_preset;
				}
				const result = await previewTemplate(body);
				expansion = result.expansion;
				previewError = null;
			} catch (err) {
				previewError = err instanceof Error ? err.message : String(err);
				expansion = null;
			}
		}, 300);

		return () => {
			if (debounceTimer) clearTimeout(debounceTimer);
		};
	});

	function insertToken(token: string) {
		const newValue = value + `{${token}}`;
		onchange(newValue);
	}

	let tokens = $derived(TOKENS[mediaType] ?? []);
</script>

<div class="flex flex-col gap-2">
	<!-- Text input -->
	<input
		type="text"
		{id}
		class="w-full rounded-md border border-gray-300 bg-white px-3 py-2 font-mono text-sm text-gray-900 focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary disabled:cursor-not-allowed disabled:opacity-50 dark:border-gray-600 dark:bg-gray-800 dark:text-gray-100"
		value={value}
		oninput={(e) => onchange((e.target as HTMLInputElement).value)}
		{disabled}
	/>

	<!-- Token chips (hidden when read-only — nothing to insert) -->
	{#if !disabled}
		<div class="flex flex-wrap gap-1.5">
			{#each tokens as token (token)}
				<button
					type="button"
					onclick={() => insertToken(token)}
					class="rounded bg-primary/10 px-2 py-0.5 font-mono text-xs font-medium text-primary hover:bg-primary/20 dark:bg-primary/20 dark:hover:bg-primary/30"
				>
					{`{${token}}`}
				</button>
			{/each}
		</div>
	{/if}

	<!-- Live preview -->
	{#if expansion !== null}
		<div class="rounded-md bg-gray-50 px-3 py-2 dark:bg-gray-800/50">
			<span class="mr-2 text-xs font-semibold uppercase tracking-wide text-gray-400 dark:text-gray-500">LIVE PREVIEW</span>
			<span class="break-all font-mono text-sm text-gray-700 dark:text-gray-300">{expansion}</span>
		</div>
	{/if}
	{#if previewError !== null}
		<div class="rounded-md bg-red-50 px-3 py-2 dark:bg-red-900/20">
			<span class="mr-2 text-xs font-semibold uppercase tracking-wide text-red-500">PREVIEW ERROR</span>
			<span class="break-all font-mono text-sm text-red-600 dark:text-red-400">{previewError}</span>
		</div>
	{/if}
</div>
