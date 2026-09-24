import { describe, it, expect, afterEach, vi } from 'vitest';
import { renderComponent, screen, fireEvent, cleanup } from '$lib/test-utils';
import CloseButton from './CloseButton.svelte';

describe('CloseButton', () => {
	afterEach(() => cleanup());

	it('fires onclick when clicked', async () => {
		const onclick = vi.fn();
		renderComponent(CloseButton, { props: { onclick } });
		await fireEvent.click(screen.getByRole('button'));
		expect(onclick).toHaveBeenCalledOnce();
	});

	it('defaults the aria-label to Close', () => {
		renderComponent(CloseButton, { props: { onclick: () => {} } });
		expect(screen.getByRole('button', { name: 'Close' })).toBeInTheDocument();
	});

	it('accepts a custom label', () => {
		renderComponent(CloseButton, { props: { onclick: () => {}, label: 'Dismiss notification' } });
		expect(screen.getByRole('button', { name: 'Dismiss notification' })).toBeInTheDocument();
	});

	it('is type="button" and renders an x glyph', () => {
		const { container } = renderComponent(CloseButton, { props: { onclick: () => {} } });
		const button = screen.getByRole('button');
		expect(button).toHaveAttribute('type', 'button');
		const path = container.querySelector('svg path');
		expect(path).toHaveAttribute('d', 'M6 18L18 6M6 6l12 12');
	});
});
