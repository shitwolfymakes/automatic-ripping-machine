import { describe, it, expect, vi, afterEach } from 'vitest';
import { renderComponent, screen, fireEvent, cleanup } from '$lib/test-utils';
import SetupStepper from '../SetupStepper.svelte';

describe('SetupStepper', () => {
	afterEach(() => cleanup());
	const progress = { account: { state: 'done' as const }, system: { state: 'attention' as const } };

	it('marks the current step and words every state', () => {
		renderComponent(SetupStepper, { props: { current: 'drives', progress, onselect: vi.fn() } });
		const current = screen.getAllByRole('button', { name: /^drives/i })[0];
		expect(current).toHaveAttribute('aria-current', 'step');
		expect(screen.getAllByText('Needs attention').length).toBeGreaterThan(0);
		expect(screen.getAllByText(/Not started · Optional/).length).toBeGreaterThan(0);
	});

	it('lets you revisit recorded steps but not jump ahead', async () => {
		const onselect = vi.fn();
		renderComponent(SetupStepper, { props: { current: 'drives', progress, onselect } });
		expect(screen.getAllByRole('button', { name: /^makemkv/i })[0]).toBeDisabled();
		await fireEvent.click(screen.getAllByRole('button', { name: /^system check/i })[0]);
		expect(onselect).toHaveBeenCalledWith('system');
	});

	it('mobile header shows the position and expands the list', async () => {
		renderComponent(SetupStepper, { props: { current: 'drives', progress, onselect: vi.fn() } });
		const toggle = screen.getByRole('button', { name: /step 3 of 9/i });
		expect(toggle).toHaveAttribute('aria-expanded', 'false');
		await fireEvent.click(toggle);
		expect(toggle).toHaveAttribute('aria-expanded', 'true');
	});
});
