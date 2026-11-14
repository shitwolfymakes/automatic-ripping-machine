import { describe, it, expect, vi, afterEach } from 'vitest';
import { renderComponent, screen, fireEvent, cleanup } from '$lib/testing/render';
import ChangePasswordForm from '../ChangePasswordForm.svelte';

// Branch pins for ChangePasswordForm, beside ChangePasswordForm.test.ts. No
// branch is left open.

vi.mock('$lib/api/auth', () => ({ changePassword: vi.fn() }));

afterEach(() => cleanup());

describe('ChangePasswordForm', () => {
	it.each([
		['current password', /current password/i, 0],
		['confirm new password', /confirm new password/i, 2]
	])('the Show password button switches the %s input to text and back', async (_name, label, index) => {
		renderComponent(ChangePasswordForm, { props: { onsuccess: vi.fn() } });
		const input = screen.getByLabelText(label) as HTMLInputElement;
		const toggle = screen.getAllByRole('button', { name: /show password/i })[index];
		expect(input.type).toBe('password');
		await fireEvent.click(toggle);
		expect(input.type).toBe('text');
		expect(toggle).toHaveAttribute('aria-pressed', 'true');
		await fireEvent.click(toggle);
		expect(input.type).toBe('password');
		expect(toggle).toHaveAttribute('aria-pressed', 'false');
	});
});
