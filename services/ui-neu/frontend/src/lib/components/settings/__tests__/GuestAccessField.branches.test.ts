import { describe, it, expect, vi, afterEach } from 'vitest';
import { tick } from 'svelte';
import { renderComponent, screen, cleanup, waitFor } from '$lib/test-utils';
import GuestAccessField from '../GuestAccessField.svelte';
import type { UserView } from '$lib/types/api.gen';

// Branch pins for GuestAccessField, beside GuestAccessField.test.ts. Two
// branches cannot be reached from the rendered component, so nothing here
// forces them:
// - The no-guest early return in apply: its callers are save, which returns
//   first when there is no guest, and toggle, which is wired only to the
//   Toggle drawn while a guest exists.
// - The no-guest side of checked: it is read only by the checkbox drawn while
//   a guest exists and by save, which returns first without one, so it is
//   never worked out while there is none.

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
	it.each([[true], [false]])('draws nothing when the users list has no guest (deferred: %s)', async (deferred) => {
		fetchUsers.mockResolvedValue([admin]);
		const { container } = renderComponent(GuestAccessField, { props: { deferred } });
		await waitFor(() => expect(fetchUsers).toHaveBeenCalledTimes(1));
		await tick();
		expect(screen.queryByTestId('guest-access-row')).toBeNull();
		expect(screen.queryByRole('checkbox')).toBeNull();
		expect(screen.queryByRole('switch')).toBeNull();
		expect(container.textContent?.trim()).toBe('');
	});
});
