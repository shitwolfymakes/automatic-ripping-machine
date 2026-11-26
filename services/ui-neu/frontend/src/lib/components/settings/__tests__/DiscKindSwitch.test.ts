import { describe, it, expect, afterEach } from 'vitest';
import { renderComponent, screen, cleanup, fireEvent } from '$lib/testing/render';
import DiscKindSwitch from '../DiscKindSwitch.svelte';

afterEach(cleanup);

describe('DiscKindSwitch', () => {
	it('names the radiogroup Disc kind', () => {
		renderComponent(DiscKindSwitch, { kind: 'bluray' });
		expect(screen.getByRole('radiogroup', { name: 'Disc kind' })).toBeInTheDocument();
	});

	it('offers Blu-ray, DVD and CD radios in that order', () => {
		renderComponent(DiscKindSwitch, { kind: 'bluray' });
		const labels = screen.getAllByRole('radio').map((r) => r.textContent);
		expect(labels).toEqual(['Blu-ray', 'DVD', 'CD']);
	});

	it('checks only the kind passed in', () => {
		renderComponent(DiscKindSwitch, { kind: 'dvd' });
		expect(screen.getByRole('radio', { name: 'DVD' })).toBeChecked();
		expect(screen.getByRole('radio', { name: 'Blu-ray' })).not.toBeChecked();
		expect(screen.getByRole('radio', { name: 'CD' })).not.toBeChecked();
	});

	it('checks a clicked radio and unchecks the previous one', async () => {
		renderComponent(DiscKindSwitch, { kind: 'bluray' });
		await fireEvent.click(screen.getByRole('radio', { name: 'CD' }));
		expect(screen.getByRole('radio', { name: 'CD' })).toBeChecked();
		expect(screen.getByRole('radio', { name: 'Blu-ray' })).not.toBeChecked();
	});
});
