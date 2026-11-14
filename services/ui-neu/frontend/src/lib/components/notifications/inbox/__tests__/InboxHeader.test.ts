import { describe, it, expect, vi, afterEach } from 'vitest';
import { renderComponent, screen, fireEvent, cleanup } from '$lib/test-utils';
import InboxHeaderHarness from './InboxHeaderHarness.svelte';

vi.mock('$lib/stores/auth', async () => {
	const { derived, writable } = await import('svelte/store');
	const _role = writable<string | null>('admin');
	return {
		role: { subscribe: _role.subscribe },
		isAdmin: derived(_role, (r) => r === 'admin'),
		// Test-only helper — not part of the real module's public API.
		__setRole: (r: string | null) => _role.set(r)
	};
});

async function setRole(role: string | null) {
	const auth = (await import('$lib/stores/auth')) as unknown as {
		__setRole: (r: string | null) => void;
	};
	auth.__setRole(role);
}

afterEach(async () => {
	cleanup();
	await setRole('admin');
});

function render(props: Record<string, unknown> = {}) {
	const onpurge = vi.fn();
	const ondismissall = vi.fn();
	renderComponent(InboxHeaderHarness, { props: { onpurge, ondismissall, ...props } });
	return { onpurge, ondismissall };
}

describe('InboxHeader', () => {
	it('renders the page title', () => {
		render();
		expect(screen.getByRole('heading', { name: 'Notifications' })).toBeInTheDocument();
	});

	it('shows the new badge when there are unseen notifications', () => {
		render({ unseenCount: 3 });
		expect(screen.getByText('3 new')).toBeInTheDocument();
	});

	it('hides the new badge when there are no unseen notifications', () => {
		render({ unseenCount: 0 });
		expect(screen.queryByText(/new$/)).not.toBeInTheDocument();
	});

	it('updates the bound showCleared when the checkbox is clicked', async () => {
		render();
		const box = screen.getByRole('checkbox', { name: 'Show dismissed' });
		expect(box).not.toBeChecked();
		expect(screen.getByTestId('show-cleared')).toHaveTextContent('false');
		await fireEvent.click(box);
		expect(box).toBeChecked();
		expect(screen.getByTestId('show-cleared')).toHaveTextContent('true');
		await fireEvent.click(box);
		expect(box).not.toBeChecked();
		expect(screen.getByTestId('show-cleared')).toHaveTextContent('false');
	});

	describe('as an admin', () => {
		it('shows Purge Cleared when there are cleared notifications and calls onpurge', async () => {
			const { onpurge } = render({ clearedCount: 2 });
			await fireEvent.click(screen.getByRole('button', { name: 'Purge Cleared' }));
			expect(onpurge).toHaveBeenCalledOnce();
		});

		it('hides Purge Cleared when nothing is cleared', () => {
			render({ clearedCount: 0 });
			expect(screen.queryByText('Purge Cleared')).not.toBeInTheDocument();
		});

		it('reads Purging... and disables the button while purging', () => {
			render({ clearedCount: 2, purging: true });
			const button = screen.getByRole('button', { name: 'Purging...' });
			expect(button).toBeDisabled();
			expect(screen.queryByText('Purge Cleared')).not.toBeInTheDocument();
		});

		it('shows Dismiss All when there are unseen notifications and calls ondismissall', async () => {
			const { ondismissall } = render({ unseenCount: 1 });
			await fireEvent.click(screen.getByRole('button', { name: 'Dismiss All' }));
			expect(ondismissall).toHaveBeenCalledOnce();
		});

		it('hides Dismiss All when nothing is unseen', () => {
			render({ unseenCount: 0 });
			expect(screen.queryByText('Dismiss All')).not.toBeInTheDocument();
		});
	});

	describe('as a guest', () => {
		it('shows neither Purge Cleared nor Dismiss All', async () => {
			await setRole('guest');
			render({ unseenCount: 2, clearedCount: 2 });
			expect(screen.queryByText('Purge Cleared')).not.toBeInTheDocument();
			expect(screen.queryByText('Dismiss All')).not.toBeInTheDocument();
		});
	});
});
