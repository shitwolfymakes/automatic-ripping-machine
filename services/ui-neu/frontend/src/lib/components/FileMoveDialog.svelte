<script lang="ts">
	import Glyph from '$lib/components/Glyph.svelte';
	import SlideOver from './SlideOver.svelte';
	import { childSubpath } from '$lib/utils/files';
	import type { MovePicker } from '$lib/stores/movePicker.svelte';

	interface Props {
		picker: MovePicker;
		count: number;
		onconfirm: () => void;
	}

	let { picker, count, onconfirm }: Props = $props();
</script>

<!-- Bulk move: a side panel that browses to the destination folder -->
<SlideOver
	open={picker.isOpen}
	title="Move {count} item{count !== 1 ? 's' : ''}"
	width="max-w-md"
	onclose={picker.close}
>
	<div class="file-move">
		<div class="file-move-main">
			<p class="file-move-subtitle">Browse to the destination folder</p>

			<!-- Current picker location -->
			<div class="flex items-center gap-2 file-move-location">
				<svg class="h-4 w-4 shrink-0 file-move-folder-icon" fill="none" stroke="currentColor" viewBox="0 0 24 24">
					<path
						stroke-linecap="round"
						stroke-linejoin="round"
						stroke-width="1.5"
						d="M3 7v10a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-6l-2-2H5a2 2 0 00-2 2z"
					/>
				</svg>
				<span class="file-move-path">{picker.displayPath()}</span>
				{#if picker.atSource}
					<span class="badge file-move-current-badge">current</span>
				{/if}
			</div>

			<!-- Folder list -->
			<div class="file-move-list">
				{#if picker.loading}
					<div class="flex items-center justify-center p-8">
						<svg class="mr-2 h-5 w-5 spin file-move-spinner" viewBox="0 0 24 24">
							<circle class="spinner-track" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" fill="none" />
							<path class="spinner-fill" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
						</svg>
					</div>
				{:else}
					{#if picker.canGoUp}
						<button type="button" onclick={picker.goUp} class="flex w-full items-center gap-3 file-move-row">
							<svg class="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
								<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M11 17l-5-5m0 0l5-5m-5 5h12" />
							</svg>
							..
						</button>
					{/if}

					{#if picker.folders.length === 0 && !picker.canGoUp}
						<div class="file-move-empty">No subfolders</div>
					{/if}

					{#each picker.folders as folder (folder.name)}
						<button
							type="button"
							onclick={() => picker.load(picker.location.root, childSubpath(picker.location.subpath, folder.name))}
							class="flex w-full items-center gap-3 file-move-row file-move-row-folder"
						>
							<svg class="h-5 w-5 shrink-0 file-move-folder-icon" fill="none" stroke="currentColor" viewBox="0 0 24 24">
								<path
									stroke-linecap="round"
									stroke-linejoin="round"
									stroke-width="1.5"
									d="M3 7v10a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-6l-2-2H5a2 2 0 00-2 2z"
								/>
							</svg>
							{folder.name}
							<Glyph name="chevron-right" class="ml-auto h-4 w-4 file-move-chevron" />
						</button>
					{/each}
				{/if}
			</div>
		</div>

		<!-- Footer, pinned to the bottom of the panel -->
		<div class="file-move-footer">
			<button type="button" onclick={picker.close} class="btn">Cancel</button>
			<button
				type="button"
				onclick={onconfirm}
				disabled={picker.atSource}
				class="btn btn-primary"
				title={picker.atSource ? 'Navigate to a different folder first' : ''}
			>
				Move here
			</button>
		</div>
	</div>
</SlideOver>

<style>
	/* The slide-over body (SlideOver.svelte) is the scrolling container with
	   p-6; this fills it as a column so the footer sits at the panel's bottom,
	   and sticky keeps it there when a long folder list scrolls (as the ISO
	   picker's footer does). */
	.file-move {
		display: flex;
		flex-direction: column;
		min-height: 100%;
	}
	.file-move-main {
		flex: 1 0 auto;
		padding-bottom: 1rem;
	}
	.file-move-subtitle {
		font-size: 0.875rem;
		line-height: 1.25rem;
		color: var(--color-text-muted);
	}
	.file-move-location {
		margin: 1rem -1.5rem 0;
		border-top: 1px solid var(--color-border);
		border-bottom: 1px solid var(--color-border);
		background: var(--color-page);
		padding: 0.5rem 1.5rem;
		font-size: 0.875rem;
		line-height: 1.25rem;
	}
	.file-move-path {
		font-weight: 500;
		color: var(--color-text);
		overflow-wrap: anywhere;
	}
	/* a plain lowercase neutral tag, not .badge's primary-tinted pill */
	.file-move-current-badge {
		border-radius: var(--radius-sm);
		padding: 0.125rem 0.375rem;
		font-size: 0.75rem;
		line-height: 1rem;
		text-transform: none;
		letter-spacing: normal;
	}
	/* rows run full-bleed across the panel, cancelling the body's p-6 */
	.file-move-list {
		margin: 0 -1.5rem;
	}
	.file-move-row {
		border-bottom: 1px solid var(--color-border);
		padding: 0.625rem 1.5rem;
		font-size: 0.875rem;
		line-height: 1.25rem;
		color: var(--color-text-secondary);
	}
	.file-move-row:hover {
		background: var(--color-primary-tint-1);
	}
	.file-move-row-folder {
		color: var(--color-text);
	}
	.file-move-empty {
		padding: 1.5rem;
		text-align: center;
		font-size: 0.875rem;
		line-height: 1.25rem;
		color: var(--color-text-muted);
	}
	.file-move-spinner {
		color: var(--color-text-faint);
	}
	.file-move-footer {
		position: sticky;
		bottom: -1.5rem;
		margin: 0 -1.5rem -1.5rem;
		display: flex;
		justify-content: flex-end;
		gap: 0.75rem;
		border-top: 1px solid var(--color-border);
		background: var(--color-surface);
		padding: 0.75rem 1.5rem;
	}
	/* :global: set on the svg / Glyph through their class */
	:global(.file-move-folder-icon) {
		color: var(--color-warning);
	}
	/* :global: set on Glyph through its class prop */
	:global(.file-move-chevron) {
		color: var(--color-text-faint);
	}
</style>
