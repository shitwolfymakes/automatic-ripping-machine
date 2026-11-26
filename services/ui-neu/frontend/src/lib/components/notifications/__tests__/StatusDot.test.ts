import { describe, it, expect, afterEach } from 'vitest';
import { renderComponent, screen, cleanup } from '$lib/testing/render';
import StatusDot from '../StatusDot.svelte';

describe('StatusDot', () => {
	afterEach(() => cleanup());

	it('exposes the status via title/aria for accessibility', () => {
		renderComponent(StatusDot, { props: { status: 'error' } });
		expect(screen.getByTitle('error')).toBeInTheDocument();
	});

	it('is an image named by its status, so the label is allowed', () => {
		renderComponent(StatusDot, { props: { status: 'error' } });
		expect(screen.getByRole('img', { name: 'error' })).toHaveClass('status-dot');
	});
});
