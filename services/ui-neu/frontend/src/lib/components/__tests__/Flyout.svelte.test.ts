import { it, expect, vi, afterEach } from 'vitest';
import { renderComponent, screen, fireEvent, cleanup } from '$lib/test-utils';
import FlyoutHarness from './FlyoutHarness.svelte';

afterEach(cleanup);

it('is closed initially — panel not rendered', () => {
	renderComponent(FlyoutHarness);
	expect(screen.queryByRole('menu')).toBeNull();
	expect(screen.getByTestId('trigger')).toHaveAttribute('aria-expanded', 'false');
});

it('toggle opens and closes the panel', async () => {
	renderComponent(FlyoutHarness);
	await fireEvent.click(screen.getByTestId('trigger'));
	expect(screen.getByRole('menu')).toBeInTheDocument();
	expect(screen.getByTestId('trigger')).toHaveAttribute('aria-expanded', 'true');
	await fireEvent.click(screen.getByTestId('trigger'));
	expect(screen.queryByRole('menu')).toBeNull();
});

it('clicking outside closes the panel', async () => {
	renderComponent(FlyoutHarness);
	await fireEvent.click(screen.getByTestId('trigger'));
	expect(screen.getByRole('menu')).toBeInTheDocument();
	await fireEvent.click(screen.getByTestId('outside'));
	expect(screen.queryByRole('menu')).toBeNull();
});

it('Escape closes the panel', async () => {
	renderComponent(FlyoutHarness);
	await fireEvent.click(screen.getByTestId('trigger'));
	expect(screen.getByRole('menu')).toBeInTheDocument();
	await fireEvent.keyDown(document, { key: 'Escape' });
	expect(screen.queryByRole('menu')).toBeNull();
});

it('an item runs its action and closes the menu', async () => {
	const onaction = vi.fn();
	renderComponent(FlyoutHarness, { props: { onaction } });
	await fireEvent.click(screen.getByTestId('trigger'));
	await fireEvent.click(screen.getByRole('menuitem', { name: /do thing/i }));
	expect(onaction).toHaveBeenCalledOnce();
	expect(screen.queryByRole('menu')).toBeNull();
});
