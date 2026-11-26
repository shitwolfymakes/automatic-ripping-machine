import { describe, it, expect, vi, afterEach } from 'vitest';
import { renderComponent, screen, cleanup } from '$lib/testing/render';
import GuestAccessField from '../GuestAccessField.svelte';

// Branch pins for GuestAccessField, beside GuestAccessField.test.ts. No
// branch is left open: toggle takes the guest from the Toggle drawn while a
// guest exists, so it has no no-guest path.

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
