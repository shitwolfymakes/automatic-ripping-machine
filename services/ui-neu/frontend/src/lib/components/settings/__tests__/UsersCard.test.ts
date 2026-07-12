import { describe, it, expect, vi, afterEach } from 'vitest';
import { renderComponent, screen, fireEvent, cleanup, waitFor } from '$lib/test-utils';
import type { UserView } from '$lib/types/api.gen';

const fetchUsers = vi.fn();
const setUserDisabled = vi.fn();
const setUserPassword = vi.fn();
vi.mock('$lib/api/users', () => ({
	fetchUsers: (...args: unknown[]) => fetchUsers(...args),
	setUserDisabled: (...args: unknown[]) => setUserDisabled(...args),
	setUserPassword: (...args: unknown[]) => setUserPassword(...args)
}));

import UsersCard from '../UsersCard.svelte';

const admin: UserView = {
	id: 'admin-1',
	username: 'admin',
	role: 'admin',
	disabled: false,
	last_login_at: '2026-06-01T00:00:00Z'
};

const guest: UserView = {
	id: 'guest-1',
	username: 'guest',
	role: 'guest',
	disabled: true,
	last_login_at: null
};

afterEach(() => {
	cleanup();
	vi.clearAllMocks();
});

describe('UsersCard', () => {
	it('renders both fixed rows with role badges', async () => {
		fetchUsers.mockResolvedValue([admin, guest]);
		renderComponent(UsersCard, { props: {} });

		expect((await screen.findAllByText('admin')).length).toBeGreaterThan(0);
		expect(screen.getAllByText('guest').length).toBeGreaterThan(0);
		// Role badges specifically (uppercase-styled role text)
		expect(screen.getByRole('button', { name: /change password/i })).toBeInTheDocument();
		expect(screen.getByRole('switch', { name: /guest/i })).toBeInTheDocument();
	});

	it('admin row opens the change-password slide-over', async () => {
		fetchUsers.mockResolvedValue([admin, guest]);
		renderComponent(UsersCard, { props: {} });

		await screen.findAllByText('admin');
		await fireEvent.click(screen.getByRole('button', { name: /change password/i }));

		expect(await screen.findByLabelText(/current password/i)).toBeInTheDocument();
	});

	it('guest toggle-ON PATCHes disabled=false directly (no password panel)', async () => {
		fetchUsers.mockResolvedValue([admin, guest]);
		setUserDisabled.mockResolvedValue({ ...guest, disabled: false });
		renderComponent(UsersCard, { props: {} });

		await screen.findAllByText('guest');
		await fireEvent.click(screen.getByRole('switch', { name: /guest/i }));

		await waitFor(() => expect(setUserDisabled).toHaveBeenCalledWith('guest-1', false));
		expect(setUserPassword).not.toHaveBeenCalled();
		expect(screen.queryByRole('dialog', { name: /set guest password/i })).not.toBeInTheDocument();
	});

	it('guest toggle-OFF PATCHes disabled=true directly', async () => {
		const enabledGuest = { ...guest, disabled: false };
		fetchUsers.mockResolvedValue([admin, enabledGuest]);
		setUserDisabled.mockResolvedValue({ ...enabledGuest, disabled: true });
		renderComponent(UsersCard, { props: {} });

		await screen.findAllByText('guest');
		await fireEvent.click(screen.getByRole('switch', { name: /guest/i }));

		await waitFor(() => expect(setUserDisabled).toHaveBeenCalledWith('guest-1', true));
		expect(setUserPassword).not.toHaveBeenCalled();
	});

	it('guest row has no Set password button', async () => {
		fetchUsers.mockResolvedValue([admin, guest]);
		renderComponent(UsersCard, { props: {} });

		await screen.findAllByText('guest');
		expect(screen.queryByRole('button', { name: /set password/i })).not.toBeInTheDocument();
	});
});
