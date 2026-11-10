import { describe, it, expect, vi, afterEach } from 'vitest';
import { renderComponent, screen, cleanup } from '$lib/test-utils';
import type { UserView } from '$lib/types/api.gen';

// Branch pins for UsersCard, beside UsersCard.test.ts. One branch cannot be
// reached from the rendered component, so nothing here forces it:
// - The warning side of roleBadgeClass: it is called only with the admin
//   user's role, which is always 'admin', so the warning class never applies.

const fetchUsers = vi.fn();
vi.mock('$lib/api/users', () => ({
	fetchUsers: (...args: unknown[]) => fetchUsers(...args),
	setUserDisabled: vi.fn(),
	setUserPassword: vi.fn()
}));
vi.mock('$lib/api/auth', () => ({ changePassword: vi.fn() }));

import UsersCard from '../UsersCard.svelte';

const admin: UserView = {
	id: 'admin-1',
	username: 'admin',
	role: 'admin',
	disabled: false,
	last_login_at: '2026-06-01T00:00:00Z'
};

afterEach(() => {
	cleanup();
	vi.clearAllMocks();
});

describe('UsersCard loading', () => {
	it('shows "Failed to load users" when the load rejects with a non-Error', async () => {
		fetchUsers.mockRejectedValue('boom');
		renderComponent(UsersCard, { props: {} });

		expect(await screen.findByText('Failed to load users')).toBeInTheDocument();
	});
});

describe('UsersCard admin row', () => {
	it('reads "Disabled" for a disabled admin', async () => {
		fetchUsers.mockResolvedValue([{ ...admin, disabled: true }]);
		renderComponent(UsersCard, { props: {} });

		expect(await screen.findByText('Disabled')).toBeInTheDocument();
		expect(screen.queryByText('Active')).not.toBeInTheDocument();
	});

	it('copes with an admin that has no last_login_at field at all', async () => {
		const { last_login_at: _omitted, ...bare } = admin;
		fetchUsers.mockResolvedValue([bare as unknown as UserView]);
		renderComponent(UsersCard, { props: {} });

		expect(await screen.findByText('Active')).toBeInTheDocument();
		expect(screen.getByText(/last login/i)).toBeInTheDocument();
	});
});
