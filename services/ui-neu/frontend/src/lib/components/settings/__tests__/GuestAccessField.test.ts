import { describe, it, expect, vi, afterEach } from 'vitest';
import { renderComponent, screen, fireEvent, cleanup, waitFor } from '$lib/test-utils';
import GuestAccessField from '../GuestAccessField.svelte';
import type { UserView } from '$lib/types/api.gen';

const fetchUsers = vi.fn();
const setUserDisabled = vi.fn();
vi.mock('$lib/api/users', () => ({
	fetchUsers: (...a: unknown[]) => fetchUsers(...a),
	setUserDisabled: (...a: unknown[]) => setUserDisabled(...a)
}));

const guest: UserView = { id: 'usr_guest', username: 'guest', role: 'guest', disabled: true, last_login_at: null };

afterEach(() => {
	cleanup();
	vi.clearAllMocks();
});

describe('GuestAccessField', () => {
	it('deferred: loads the guest, saves only on save() and only when changed', async () => {
		fetchUsers.mockResolvedValue([guest]);
		setUserDisabled.mockResolvedValue({ ...guest, disabled: false });
		const { component } = renderComponent(GuestAccessField, { props: { deferred: true } });
		const box = (await screen.findByRole('checkbox', { name: /without signing in/i })) as HTMLInputElement;
		expect(box.checked).toBe(false);
		const c = component as unknown as { save(): Promise<void> };
		await c.save();
		expect(setUserDisabled).not.toHaveBeenCalled();
		await fireEvent.click(box);
		await c.save();
		expect(setUserDisabled).toHaveBeenCalledWith('usr_guest', false);
	});

	it('immediate (Settings): the switch saves at once and reports back', async () => {
		const onsaved = vi.fn();
		setUserDisabled.mockResolvedValue({ ...guest, disabled: false });
		renderComponent(GuestAccessField, { props: { guest, onsaved } });
		await fireEvent.click(screen.getByRole('switch', { name: /guest/i }));
		await waitFor(() => expect(setUserDisabled).toHaveBeenCalledWith('usr_guest', false));
		expect(onsaved).toHaveBeenCalledWith(true);
		expect(fetchUsers).not.toHaveBeenCalled();
	});

	it('reports a failed save', async () => {
		const onerror = vi.fn();
		setUserDisabled.mockRejectedValue(new Error('nope'));
		renderComponent(GuestAccessField, { props: { guest, onerror } });
		await fireEvent.click(screen.getByRole('switch', { name: /guest/i }));
		await waitFor(() => expect(onerror).toHaveBeenCalledWith('nope'));
	});

	it('renders nothing without a guest account', async () => {
		fetchUsers.mockRejectedValue(new Error('x'));
		const { container } = renderComponent(GuestAccessField, { props: { deferred: true } });
		await waitFor(() => expect(fetchUsers).toHaveBeenCalled());
		expect(container.querySelector('[data-testid="guest-access-row"]')).toBeNull();
	});
});
