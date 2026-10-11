import { describe, it, expect, vi, afterEach } from 'vitest';
import { renderComponent, screen, fireEvent, cleanup } from '$lib/test-utils';
import ChoiceCard from '../ChoiceCard.svelte';

const options = [
	{ value: 'beta', title: 'Use the free beta key', description: 'Renews monthly.', badge: 'Default' },
	{ value: 'own', title: 'I have a purchased key', description: 'Never expires.' }
];

describe('ChoiceCard', () => {
	afterEach(() => cleanup());

	it('renders a radio per option with the selected one checked', () => {
		renderComponent(ChoiceCard, { props: { name: 'k', value: 'beta', options, onchange: vi.fn() } });
		expect(screen.getByRole('radio', { name: /free beta key/i })).toBeChecked();
		expect(screen.getByRole('radio', { name: /purchased key/i })).not.toBeChecked();
		expect(screen.getByText('Default')).toBeInTheDocument();
		expect(screen.getByText('Never expires.')).toBeInTheDocument();
	});

	it('calls onchange with the picked value', async () => {
		const onchange = vi.fn();
		renderComponent(ChoiceCard, { props: { name: 'k', value: 'beta', options, onchange } });
		await fireEvent.click(screen.getByRole('radio', { name: /purchased key/i }));
		expect(onchange).toHaveBeenCalledWith('own');
	});

	it('disables every option when disabled', () => {
		renderComponent(ChoiceCard, { props: { name: 'k', value: 'beta', options, onchange: vi.fn(), disabled: true } });
		for (const r of screen.getAllByRole('radio')) expect(r).toBeDisabled();
	});
});
