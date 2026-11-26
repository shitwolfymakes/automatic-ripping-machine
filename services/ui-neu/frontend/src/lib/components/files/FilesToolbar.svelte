<script lang="ts">
	import Glyph from '$lib/components/shared/Glyph.svelte';
	import { isAdmin } from '$lib/stores/auth';
	import { features } from '$lib/features';
	import type { FilesBrowser } from '$lib/stores/files-browser.svelte';

	interface Props {
		browser: FilesBrowser;
		onmove: () => void;
		onbulkdelete: () => void;
		onorphans: () => void;
		oncleanup: () => void;
		onnewfolder: () => void;
	}

	let { browser, onmove, onbulkdelete, onorphans, oncleanup, onnewfolder }: Props = $props();
</script>

<div class="cluster shrink-0 files-page-toolbar">
	<!-- Bulk move (visible when items selected) -->
	{#if browser.selectedKeys.size > 0 && $isAdmin}
		<button type="button" onclick={onmove} disabled={browser.isReadonly} class="btn btn-primary files-page-bulk-btn">
			<svg class="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
				<path
					stroke-linecap="round"
					stroke-linejoin="round"
					stroke-width="2"
					d="M7 16V4m0 0L3 8m4-4l4 4m6 0v12m0 0l4-4m-4 4l-4-4"
				/>
			</svg>
			Move {browser.selectedKeys.size}
		</button>
		<button
			type="button"
			onclick={onbulkdelete}
			disabled={browser.isReadonly}
			class="btn files-page-bulk-btn files-page-bulk-btn-danger"
		>
			<Glyph name="trash" class="h-4 w-4" />
			Delete {browser.selectedKeys.size}
		</button>
	{/if}
	{#if $isAdmin && features.maintenance}
		<!-- Orphan folders -->
		<button type="button" onclick={onorphans} class="btn btn-icon files-page-toolbar-btn" title="Orphan folders">
			<Glyph name="folder-plus" class="h-5 w-5" />
		</button>
		<!-- Transcoder cleanup -->
		<button
			type="button"
			onclick={oncleanup}
			class="btn btn-icon files-page-toolbar-btn"
			title="Clean up transcoder jobs"
		>
			<svg class="h-5 w-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
				<path
					stroke-linecap="round"
					stroke-linejoin="round"
					stroke-width="2"
					d="M7 4v16M17 4v16M3 8h4m10 0h4M3 12h18M3 16h4m10 0h4M4 20h16a1 1 0 001-1V5a1 1 0 00-1-1H4a1 1 0 00-1 1v14a1 1 0 001 1z"
				/>
			</svg>
		</button>
	{/if}
	<!-- New folder -->
	{#if $isAdmin}
		<button
			type="button"
			onclick={onnewfolder}
			disabled={browser.isReadonly}
			class="btn btn-icon files-page-toolbar-btn"
			title={browser.isReadonly ? 'Read-only mount' : 'New folder'}
		>
			<Glyph name="folder-plus" class="h-5 w-5" />
		</button>
	{/if}
	<!-- Refresh -->
	<button
		type="button"
		onclick={() => browser.navigate(browser.current.root, browser.current.subpath)}
		disabled={browser.loading}
		class="btn btn-icon files-page-toolbar-btn"
		title="Refresh"
	>
		<Glyph name="refresh" class="h-5 w-5 {browser.loading ? 'spin' : ''}" />
	</button>
</div>

<style>
	.files-page-toolbar {
		gap: 0.25rem;
	}
	/* padding is 0.5rem all around, not .btn-icon's own 0.375rem default */
	.files-page-toolbar-btn {
		padding: 0.5rem;
	}
	/* bulk-action buttons are text-xs (0.75rem/1rem) with 0.375rem/0.75rem padding, smaller than
	   .btn's own default 1rem/0.5rem/text-sm - restated here; the icon+label gap is close enough to
	   .btn's own 0.375rem default that no override is needed there */
	.files-page-bulk-btn {
		padding: 0.375rem 0.75rem;
		font-size: 0.75rem;
		line-height: 1rem;
	}
	.files-page-bulk-btn-danger {
		border: 0;
		background: var(--color-danger);
		color: var(--color-on-primary);
	}
	/* darkens on hover;
	   no darker danger token exists, so filter substitutes for a literal
	   colour (the lint bans raw colour keywords, even inside color-mix) */
	.files-page-bulk-btn-danger:hover {
		filter: brightness(0.9);
	}
</style>
