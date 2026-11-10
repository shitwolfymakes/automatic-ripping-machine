import { describe, it, expect, vi, afterEach } from 'vitest';
import { tick } from 'svelte';
import { renderComponent, screen, fireEvent, cleanup, waitFor } from '$lib/test-utils';
import GuestAccessField from '../GuestAccessField.svelte';
import type { UserView } from '$lib/types/api.gen';

// Branch pins for GuestAccessField, beside GuestAccessField.test.ts. One
// branch cannot be reached from the rendered component, so nothing here
// forces it:
// - The no-guest early return in apply: its one caller is toggle, which is
//   wired only to the Toggle drawn while a guest exists.

const fetchUsers = vi.fn();
vi.mock('$lib/api/users', () => ({
	fetchUsers: (...a: unknown[]) => fetchUsers(...a),
	setUserDisabled: vi.fn()
}));

afterEach(() => {
	cleanup();
	vi.clearAllMocks();
});

const admin: UserView = { id: 'usr_admin', username: 'admin', role: 'admin', disabled: false, last_login_at: null };

describe('GuestAccessField', () => {
	it('draws nothing when the users list has no guest', async () => {
		fetchUsers.mockResolvedValue([admin]);
		const { container } = renderComponent(GuestAccessField);
		await waitFor(() => expect(fetchUsers).toHaveBeenCalledTimes(1));
		await tick();
		expect(screen.queryByTestId('guest-access-row')).toBeNull();
		expect(screen.queryByRole('checkbox')).toBeNull();
		expect(screen.queryByRole('switch')).toBeNull();
		expect(container.textContent?.trim()).toBe('');
	});

	it('shows the saved state of a guest it loaded itself', async () => {
		fetchUsers.mockResolvedValue([{ ...admin, id: 'usr_guest', username: 'guest', role: 'guest', disabled: true }]);
		renderComponent(GuestAccessField);
		expect(await screen.findByText('Off')).toBeInTheDocument();
		await fireEvent.click(screen.getByRole('switch', { name: /guest/i }));
		await waitFor(() => expect(screen.getByText('On')).toBeInTheDocument());
	});
});
