<script lang="ts">
	// The shared editor sidebar on Settings > Sessions: a right-docked slide-over
	// with the title, an optional action button and Close in the header, a
	// scrolling body and a footer pinned below it (usage line, Cancel, Save).
	// Sessions, rip presets and transcode presets are all edited in this shell.
	import type { Snippet } from 'svelte';
	import SlideOver from './SlideOver.svelte';

	interface Props {
		open?: boolean;
		title: string;
		/** 'form' fits a plain form; 'wide' suits the transcode preset's settings tabs. */
		width: 'form' | 'wide';
		/** Opened over another sidebar. */
		stacked?: boolean;
		headerActions?: Snippet;
		/** Omit to draw no footer strip at all. */
		footer?: Snippet;
		children: Snippet;
		onclose: () => void;
	}

	let {
		open = $bindable(true),
		title,
		width,
		stacked = false,
		headerActions,
		footer: footerContent,
		children,
		onclose
	}: Props = $props();
</script>

{#snippet footerStrip()}
	<footer class="editor-sidebar-footer" data-testid="editor-sidebar-footer">
		{@render footerContent!()}
	</footer>
{/snippet}

<SlideOver
	bind:open
	{title}
	width="editor-sidebar-{width}"
	{stacked}
	{headerActions}
	footer={footerContent ? footerStrip : undefined}
	{onclose}
>
	{@render children()}
</SlideOver>

<style>
	/* :global because SlideOver renders the panel; the form width fits a plain form. */
	:global(.slide-over-panel.editor-sidebar-form) {
		width: 100%;
		max-width: 32rem;
	}
	/* :global for the same reason; 640 px suits the transcode preset's settings tabs. */
	:global(.slide-over-panel.editor-sidebar-wide) {
		width: 100%;
		max-width: 40rem;
	}
	.editor-sidebar-footer {
		flex: none;
		display: flex;
		flex-direction: column;
		gap: 0.5rem;
		padding: 0.75rem 1.5rem;
		border-top: 1px solid var(--color-border);
		background: var(--color-surface);
	}
</style>
