/**
 * Svelte action that moves the node to document.body (or a given target).
 *
 * Use for overlays — modals, slide-overs, dropdowns — that must escape any
 * ancestor that establishes a containing block for `position: fixed`
 * (a transform, filter, backdrop-filter, perspective, will-change, or
 * `contain` on a parent). Without portaling, a fixed child is positioned
 * relative to that ancestor instead of the viewport.
 */
export function portal(node: HTMLElement, target: HTMLElement | string = document.body) {
	let dest: HTMLElement | null;

	function mount(t: HTMLElement | string) {
		dest = typeof t === 'string' ? document.querySelector<HTMLElement>(t) : t;
		if (dest) dest.appendChild(node);
	}

	mount(target);

	return {
		update(t: HTMLElement | string) {
			mount(t);
		},
		destroy() {
			node.parentNode?.removeChild(node);
		},
	};
}
