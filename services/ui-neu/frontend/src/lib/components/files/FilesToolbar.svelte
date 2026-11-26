<script lang="ts">
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
			<svg class="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
				<path
					stroke-linecap="round"
					stroke-linejoin="round"
					stroke-width="2"
					d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"
				/>
			</svg>
			Delete {browser.selectedKeys.size}
		</button>
	{/if}
	{#if $isAdmin && features.maintenance}
		<!-- Orphan folders -->
		<button type="button" onclick={onorphans} class="btn btn-icon files-page-toolbar-btn" title="Orphan folders">
			<svg class="h-5 w-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
				<path
					stroke-linecap="round"
					stroke-linejoin="round"
					stroke-width="2"
					d="M3 7v10a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-6l-2-2H5a2 2 0 00-2 2z"
				/>
				<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 11v4m-2-2h4" />
			</svg>
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
			<svg class="h-5 w-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
				<path
					stroke-linecap="round"
					stroke-linejoin="round"
					stroke-width="2"
					d="M9 13h6m-3-3v6m-9 1V7a2 2 0 012-2h6l2 2h6a2 2 0 012 2v8a2 2 0 01-2 2H5a2 2 0 01-2-2z"
				/>
			</svg>
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
		<svg class="h-5 w-5 {browser.loading ? 'spin' : ''}" fill="none" stroke="currentColor" viewBox="0 0 24 24">
			<path
				stroke-linecap="round"
				stroke-linejoin="round"
				stroke-width="2"
				d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"
			/>
		</svg>
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
