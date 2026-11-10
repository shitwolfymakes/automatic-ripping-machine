// A press outside a menu: listens on the document in the capture
// phase, so a press that an inner handler stops still counts.

/** Calls `handler` for each `type` event whose target is outside every
 * node `inside` returns (a node not set yet counts as not containing
 * it). `inside` runs at event time, so it sees nodes bound after the
 * listener starts. Returns the function that stops listening. */
export function onOutsideClick(
	type: 'click' | 'mousedown',
	inside: () => (Node | null | undefined)[],
	handler: () => void
): () => void {
	function listener(ev: Event) {
		const target = ev.target as Node;
		if (inside().some((node) => node?.contains(target))) return;
		handler();
	}
	document.addEventListener(type, listener, true);
	return () => document.removeEventListener(type, listener, true);
}
