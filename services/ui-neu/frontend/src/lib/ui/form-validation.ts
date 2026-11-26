// Save-blocking validation shared by the editors: Save stays clickable, and a
// Save with invalid input marks each invalid field (aria-invalid plus a
// message under it) and moves focus to the first invalid field in form order.
import { tick } from 'svelte';

/** Field id -> the message shown under that field. */
export type FieldErrors = Record<string, string>;

export const NAME_REQUIRED = 'Name is required';

/** The first id in `order` that has an error, or null when none does. */
export function firstInvalid(errors: FieldErrors, order: string[]): string | null {
	return order.find((id) => id in errors) ?? null;
}

/** The required-name rule: a blank or whitespace-only name is an error on `id`. */
export function nameErrors(id: string, name: string): FieldErrors {
	return name.trim() ? {} : { [id]: NAME_REQUIRED };
}

/** The id of the message element under the field `fieldId`. */
export function errorId(fieldId: string): string {
	return `${fieldId}-error`;
}

/** The aria attributes a control spreads: invalid and described by its message while it has one. */
export function invalidAttrs(
	fieldId: string,
	message: string | undefined
): { 'aria-invalid'?: 'true'; 'aria-describedby'?: string } {
	return message ? { 'aria-invalid': 'true', 'aria-describedby': errorId(fieldId) } : {};
}

/** Focuses the element with `id` and scrolls it to the middle of its scroller. */
export function focusField(id: string): void {
	const el = document.getElementById(id);
	if (!el) return;
	el.focus();
	// jsdom has no scrollIntoView.
	el.scrollIntoView?.({ block: 'center' });
}

/** Focuses the first invalid field once the DOM shows its mark; false when nothing is invalid. */
export async function focusFirstInvalid(errors: FieldErrors, order: string[]): Promise<boolean> {
	const id = firstInvalid(errors, order);
	if (id === null) return false;
	await tick();
	focusField(id);
	return true;
}
