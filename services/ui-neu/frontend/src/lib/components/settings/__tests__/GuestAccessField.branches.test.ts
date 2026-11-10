import { describe, it, expect, vi, afterEach } from 'vitest';
import { renderComponent, screen, cleanup } from '$lib/test-utils';
import GuestAccessField from '../GuestAccessField.svelte';

// Branch pins for GuestAccessField, beside GuestAccessField.test.ts. One
// branch cannot be reached from the rendered component, so nothing here
// forces it:
// - The no-guest early return in toggle: it is wired only to the Toggle
//   drawn while a guest exists.

vi.mock('$lib/api/users', () => ({
	setUserDisabled: vi.fn()
}));

afterEach(() => {
	cleanup();
	vi.clearAllMocks();
});

describe('GuestAccessField', () => {
	it('draws nothing when there is no guest account', () => {
		const { container } = renderComponent(GuestAccessField, { props: { guest: null } });
		expect(screen.queryByTestId('guest-access-row')).toBeNull();
		expect(screen.queryByRole('switch')).toBeNull();
		expect(container.textContent?.trim()).toBe('');
	});
});
