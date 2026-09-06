<script lang="ts">
	import type { Snippet } from 'svelte';
	import { portal } from '$lib/actions/portal';

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
		<div role="presentation" class="fixed inset-0 z-40 bg-black/40" onclick={close}></div>

		<!-- Panel -->
		<div
			role="dialog"
			aria-modal="true"
			aria-label={title}
			class="fixed inset-y-0 right-0 z-50 flex w-full {width} flex-col bg-white shadow-xl dark:bg-gray-900"
		>
			<div class="flex items-center justify-between border-b border-gray-200 px-6 py-4 dark:border-gray-700">
				<h2 class="text-lg font-semibold text-gray-900 dark:text-white">{title}</h2>
				<div class="flex items-center gap-2">
					{#if headerActions}{@render headerActions()}{/if}
					<button
						type="button"
						aria-label="Close"
						onclick={close}
						class="rounded-md p-1 text-gray-400 hover:bg-gray-100 hover:text-gray-600 dark:hover:bg-gray-800 dark:hover:text-gray-300"
					>
						<svg class="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" /></svg>
					</button>
				</div>
			</div>

			<div class="flex-1 overflow-y-auto p-6">
				{@render children()}
			</div>
		</div>
	</div>
{/if}
