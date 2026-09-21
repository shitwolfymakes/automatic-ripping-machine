import { it, expect, vi, afterEach } from 'vitest';
import { renderComponent, screen, fireEvent, cleanup } from '$lib/test-utils';
import SlideOverHarness from './SlideOverHarness.svelte';

afterEach(cleanup);

it('renders title and body when open', () => {
	renderComponent(SlideOverHarness, { props: { open: true } });
	expect(screen.getByRole('dialog', { name: /panel title/i })).toBeInTheDocument();
	expect(screen.getByTestId('body')).toBeInTheDocument();
});

it('renders nothing when closed', () => {
	renderComponent(SlideOverHarness, { props: { open: false } });
	expect(screen.queryByRole('dialog')).toBeNull();
});

it('close button dismisses and fires onclose', async () => {
	const onclose = vi.fn();
	renderComponent(SlideOverHarness, { props: { open: true, onclose } });
	await fireEvent.click(screen.getByRole('button', { name: /close/i }));
	expect(onclose).toHaveBeenCalledOnce();
	expect(screen.queryByRole('dialog')).toBeNull();
});

it('Escape dismisses the panel', async () => {
	renderComponent(SlideOverHarness, { props: { open: true } });
	expect(screen.getByRole('dialog')).toBeInTheDocument();
	await fireEvent.keyDown(document, { key: 'Escape' });
	expect(screen.queryByRole('dialog')).toBeNull();
});
