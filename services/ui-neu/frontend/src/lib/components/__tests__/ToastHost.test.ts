import { describe, it, expect, afterEach } from 'vitest';
import { renderComponent, screen, fireEvent, cleanup } from '$lib/test-utils';
import ToastHost from '../ToastHost.svelte';
import { addToast, toasts, dismissToast } from '$lib/stores/toast.svelte';

describe('ToastHost', () => {
	afterEach(() => {
		for (const t of toasts.value) dismissToast(t.id);
		cleanup();
	});

	it('renders an active toast', async () => {
		addToast({ tone: 'success', title: 'Saved', body: 'All good' });
		renderComponent(ToastHost);
		expect(await screen.findByText('Saved')).toBeInTheDocument();
		expect(screen.getByText('All good')).toBeInTheDocument();
	});

	it('dismisses a toast when its close button is clicked', async () => {
		addToast({ tone: 'info', title: 'Closable' });
		renderComponent(ToastHost);
		await fireEvent.click(screen.getByRole('button', { name: /dismiss/i }));
		expect(screen.queryByText('Closable')).toBeNull();
	});

	it('renders a toast link when one is given', async () => {
		addToast({
			tone: 'success',
			title: 'ISO rip started',
			body: 'a.iso is in the ripping queue.',
			link: { href: '/', label: 'View card' }
		});
		renderComponent(ToastHost);
		const link = await screen.findByRole('link', { name: 'View card' });
		expect(link).toHaveAttribute('href', '/');
	});

	it('renders no link when the toast does not carry one', async () => {
		addToast({ tone: 'info', title: 'No link here' });
		renderComponent(ToastHost);
		await screen.findByText('No link here');
		expect(screen.queryByRole('link')).not.toBeInTheDocument();
	});
});
