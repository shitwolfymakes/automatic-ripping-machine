import { describe, it, expect, afterEach } from 'vitest';
import { render, screen, cleanup } from '@testing-library/svelte';
import ComingSoon from '../ComingSoon.svelte';

afterEach(() => cleanup());

describe('ComingSoon', () => {
	it('renders the label and a Coming soon badge', () => {
		render(ComingSoon, { props: { label: 'Fix Permissions' } });
		expect(screen.getByText('Fix Permissions')).toBeInTheDocument();
		expect(screen.getByText(/coming soon/i)).toBeInTheDocument();
	});

	it('renders a disabled button', () => {
		render(ComingSoon, { props: { label: 'Fix Permissions' } });
		const btn = screen.getByRole('button', { name: /fix permissions/i });
		expect(btn).toBeDisabled();
	});

	it('exposes the feature in the title tooltip', () => {
		render(ComingSoon, { props: { label: 'Submit', feature: 'CRC submit' } });
		const btn = screen.getByRole('button', { name: /submit/i });
		expect(btn.getAttribute('title')).toMatch(/CRC submit/i);
	});
});
