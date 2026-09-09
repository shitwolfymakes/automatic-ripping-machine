<script lang="ts">
	import type { Snippet } from 'svelte';
	import { portal } from '$lib/actions/portal';
	import CloseButton from './CloseButton.svelte';

	interface Props {
		/** Whether the panel is shown. Bindable so callers can also close it. */
		open?: boolean;
		/** Header title text. */
		title: string;
		/** Panel body. */
		children: Snippet;
		/** Optional extra header content (right of the title, before the close button). */
		headerActions?: Snippet;
		/** Width utility for the panel (defaults to a comfortable form width). */
		width?: string;
		/** Called when the user dismisses (backdrop, ✕, or Escape). */
		onclose?: () => void;
	}

	let {
		open = $bindable(false),
		title,
		children,
		headerActions,
		width = 'max-w-lg',
		onclose,
	}: Props = $props();

	function close() {
		open = false;
		onclose?.();
	}

	// Close on Escape while open.
	$effect(() => {
		if (!open) return;
		function onKeydown(e: KeyboardEvent) {
			if (e.key === 'Escape') close();
		}
		document.addEventListener('keydown', onKeydown);
		return () => document.removeEventListener('keydown', onKeydown);
	});
</script>

{#if open}
	<!-- Portaled to <body> so the fixed panel escapes any ancestor that creates
	     a containing block (transform/filter/backdrop-filter/will-change). -->
	<div use:portal>
		<!-- Backdrop -->
		<div role="presentation" class="slide-over-scrim fixed inset-0" onclick={close}></div>

		<!-- Panel -->
		<div
			role="dialog"
			aria-modal="true"
			aria-label={title}
			class="slide-over-panel slide-over-panel-fixed fixed flex {width}"
		>
			<div class="slide-over-header">
				<h2 class="modal-title">{title}</h2>
				<div class="flex items-center gap-2">
					{#if headerActions}{@render headerActions()}{/if}
					<CloseButton onclick={close} />
				</div>
			</div>

			<div class="flex-1 overflow-y-auto p-6">
				{@render children()}
			</div>
		</div>
	</div>
{/if}

<style>
	/* SlideOver renders the backdrop and panel as two separate portaled
	   elements (not slide-over.css's single flex-end wrapper), so it needs
	   its own fixed positioning + z-index; the panel keeps slide-over-panel's
	   surface/border/shadow via that shared class. */
	.slide-over-scrim {
		z-index: 40;
		background: var(--color-backdrop);
	}
	.slide-over-panel-fixed {
		z-index: 50;
		top: 0;
		bottom: 0;
		right: 0;
		flex-direction: column;
	}
</style>
