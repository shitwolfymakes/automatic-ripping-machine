// Tells whether a key event's target takes typed text.

/** The element takes typed text: an input, a textarea, or contentEditable. */
export function isTextField(target: HTMLElement | null): boolean {
	return target !== null && (target.tagName === 'INPUT' || target.tagName === 'TEXTAREA' || target.isContentEditable);
}
