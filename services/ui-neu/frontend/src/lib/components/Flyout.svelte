<script lang="ts">
	import type { Snippet } from 'svelte';
	import { tick } from 'svelte';
	import { reveal } from '$lib/transitions';

	interface Props {
		/** Trigger content. Receives `toggle` (flip open/closed) and the current `open` state. */
		trigger: Snippet<[{ toggle: () => void; open: boolean }]>;
		/** Panel content. Receives `close` so items can dismiss the menu after acting. */
		children: Snippet<[{ close: () => void }]>;
		/** Horizontal edge the panel aligns to. */
		align?: 'left' | 'right';
		/** Panel width utility class (e.g. 'w-52', 'w-60'). */
		width?: string;
		/** Optional bindable open state for callers that need to drive it. */
		open?: boolean;
		/** Extra classes for the panel (rarely needed). */
		panelClass?: string;
		/** Default vertical padding for a menu (override via panelClass for form panels). */
		paddingClass?: string;
		/** Gap in px between the trigger and the panel. */
		gap?: number;
		/** Accessible label for the menu panel. */
		label?: string;
	}

	let {
		trigger,
		children,
		align = 'right',
		width = 'w-52',
		open = $bindable(false),
		panelClass = '',
		paddingClass = 'py-1',
		gap = 6,
		label = 'Menu',
	}: Props = $props();

	let root = $state<HTMLElement>();
	let panel = $state<HTMLElement>();

	// The panel is position:fixed so it escapes any overflow:hidden/auto ancestor
	// (cards, scroll regions). We anchor it to the trigger's viewport rect.
	let pos = $state<{ top: number; left?: number; right?: number; maxHeight: number } | null>(null);

	function place() {
		if (!root) return;
		const r = root.getBoundingClientRect();
		const margin = 8;
		const top = r.bottom + gap;
		const maxHeight = Math.max(120, window.innerHeight - top - margin);
		if (align === 'right') {
			pos = { top, right: Math.max(margin, window.innerWidth - r.right), maxHeight };
		} else {
			pos = { top, left: Math.max(margin, r.left), maxHeight };
		}
	}

	function toggle() {
		open = !open;
	}
	function close() {
		open = false;
	}

	// Position on open; reposition on scroll/resize while open. Close on outside
	// click (capture phase, before inner stopPropagation) and on Escape.
	$effect(() => {
		if (!open) {
			pos = null;
			return;
		}

		place();
		// Re-measure after the panel mounts (so its own size is known if needed).
		tick().then(place);

		function onPointerDown(e: MouseEvent) {
			const t = e.target as Node;
			if (root && root.contains(t)) return;
			if (panel && panel.contains(t)) return;
			close();
		}
		function onKeydown(e: KeyboardEvent) {
			if (e.key === 'Escape') close();
		}
		function reposition() {
			place();
		}

		document.addEventListener('click', onPointerDown, true);
		document.addEventListener('keydown', onKeydown);
		window.addEventListener('scroll', reposition, true);
		window.addEventListener('resize', reposition);
		return () => {
			document.removeEventListener('click', onPointerDown, true);
			document.removeEventListener('keydown', onKeydown);
			window.removeEventListener('scroll', reposition, true);
			window.removeEventListener('resize', reposition);
		};
	});
</script>

<span class="inline-flex" bind:this={root}>
	{@render trigger({ toggle, open })}
</span>

{#if open && pos}
	<div
		bind:this={panel}
		in:reveal
		role="menu"
		aria-label={label}
		style="position: fixed; top: {pos.top}px; {pos.right !== undefined ? `right: ${pos.right}px;` : `left: ${pos.left}px;`} max-height: {pos.maxHeight}px;"
		class="z-50 {width} overflow-y-auto rounded-lg border border-primary/20 bg-surface {paddingClass} shadow-lg dark:border-primary/30 dark:bg-surface-dark {panelClass}"
	>
		{@render children({ close })}
	</div>
{/if}
