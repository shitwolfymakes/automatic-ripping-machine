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

const changePassword = vi.fn();
vi.mock('$lib/api/auth', () => ({
	changePassword: (...args: unknown[]) => changePassword(...args)
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
	it('renders the admin row with its badge and the guest access switch', async () => {
		fetchUsers.mockResolvedValue([admin, guest]);
		renderComponent(UsersCard, { props: {} });

		expect((await screen.findAllByText('admin')).length).toBeGreaterThan(0);
		expect(screen.getByRole('button', { name: /change password/i })).toBeInTheDocument();
		// Guests never sign in, so the guest row is just the access switch: no
		// username, role badge, status or last-login line.
		expect(screen.getByText('Guest access')).toBeInTheDocument();
		expect(screen.getByRole('switch', { name: /guest/i })).toBeInTheDocument();
		expect(screen.queryByText('Last login: N/A')).toBeNull();
		expect(screen.getAllByText(/last login/i)).toHaveLength(1);
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

		await screen.findByText('Guest access');
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

		await screen.findByText('Guest access');
		await fireEvent.click(screen.getByRole('switch', { name: /guest/i }));

		await waitFor(() => expect(setUserDisabled).toHaveBeenCalledWith('guest-1', true));
		expect(setUserPassword).not.toHaveBeenCalled();
	});

	it('guest row has no Set password button', async () => {
		fetchUsers.mockResolvedValue([admin, guest]);
		renderComponent(UsersCard, { props: {} });

		await screen.findByText('Guest access');
		expect(screen.queryByRole('button', { name: /set password/i })).not.toBeInTheDocument();
	});

	it('closes the change-password slide-over via the Close button', async () => {
		fetchUsers.mockResolvedValue([admin, guest]);
		renderComponent(UsersCard, { props: {} });

		await screen.findAllByText('admin');
		await fireEvent.click(screen.getByRole('button', { name: /change password/i }));
		expect(await screen.findByLabelText(/current password/i)).toBeInTheDocument();

		await fireEvent.click(screen.getByRole('button', { name: /close/i }));

		await waitFor(() =>
			expect(screen.queryByLabelText(/current password/i)).not.toBeInTheDocument()
		);
	});

	it('closes the slide-over and reports success after a password change', async () => {
		fetchUsers.mockResolvedValue([admin, guest]);
		changePassword.mockResolvedValue({});
		renderComponent(UsersCard, { props: {} });

		await screen.findAllByText('admin');
		await fireEvent.click(screen.getByRole('button', { name: /change password/i }));

		await fireEvent.input(await screen.findByLabelText(/current password/i), {
			target: { value: 'oldpass1' }
		});
		await fireEvent.input(screen.getByLabelText(/^new password$/i), {
			target: { value: 'newpassword1' }
		});
		await fireEvent.input(screen.getByLabelText(/confirm new password/i), {
			target: { value: 'newpassword1' }
		});
		await fireEvent.click(screen.getByRole('button', { name: /set new password/i }));

		expect(await screen.findByText(/admin password changed/i)).toBeInTheDocument();
		expect(screen.queryByLabelText(/current password/i)).not.toBeInTheDocument();
	});

	it('surfaces an error when the guest toggle PATCH fails', async () => {
		fetchUsers.mockResolvedValue([admin, guest]);
		setUserDisabled.mockRejectedValue(new Error('backend unreachable'));
		renderComponent(UsersCard, { props: {} });

		await screen.findByText('Guest access');
		await fireEvent.click(screen.getByRole('switch', { name: /guest/i }));

		expect(await screen.findByText(/backend unreachable/i)).toBeInTheDocument();
		// The switch still reads Off: a failed PATCH must not look like a win.
		expect(screen.getByTestId('guest-access-row')).toHaveTextContent('Off');
		expect(screen.getByRole('switch', { name: /guest/i })).toHaveAttribute('aria-checked', 'false');
	});

	it('falls back to a generic message when the toggle rejects a non-Error', async () => {
		fetchUsers.mockResolvedValue([admin, guest]);
		setUserDisabled.mockRejectedValue('boom');
		renderComponent(UsersCard, { props: {} });

		await screen.findByText('Guest access');
		await fireEvent.click(screen.getByRole('switch', { name: /guest/i }));

		expect(await screen.findByText(/failed to update guest access/i)).toBeInTheDocument();
	});

	it('auto-dismisses the feedback banner after 4 seconds', async () => {
		vi.useFakeTimers();
		try {
			fetchUsers.mockResolvedValue([admin, guest]);
			setUserDisabled.mockResolvedValue({ ...guest, disabled: false });
			renderComponent(UsersCard, { props: {} });

			await vi.advanceTimersByTimeAsync(0);
			await fireEvent.click(screen.getByRole('switch', { name: /guest/i }));
			await vi.advanceTimersByTimeAsync(0);
			expect(screen.getByText(/guest access enabled/i)).toBeInTheDocument();

			await vi.advanceTimersByTimeAsync(4000);
			expect(screen.queryByText(/guest access enabled/i)).not.toBeInTheDocument();
		} finally {
			vi.useRealTimers();
		}
	});

	it('reports an error when the initial user load fails', async () => {
		fetchUsers.mockRejectedValue(new Error('users endpoint down'));
		renderComponent(UsersCard, { props: {} });

		expect(await screen.findByText(/users endpoint down/i)).toBeInTheDocument();
		expect(screen.queryByRole('switch', { name: /guest/i })).not.toBeInTheDocument();
	});
});
