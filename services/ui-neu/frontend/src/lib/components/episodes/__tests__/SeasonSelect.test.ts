import { describe, it, expect, vi, afterEach } from 'vitest';
import { renderComponent, screen, cleanup, fireEvent } from '$lib/test-utils';
import SeasonSelect from '../SeasonSelect.svelte';

afterEach(cleanup);

const render = (props: Record<string, unknown>) => {
	const onchange = vi.fn();
	renderComponent(SeasonSelect, { props: { ariaLabel: 'Season', onchange, ...props } });
	return { onchange, control: screen.getByLabelText('Season') as HTMLSelectElement | HTMLInputElement };
};
const options = (el: HTMLSelectElement) => [...el.options].map((o) => [o.value, o.text]);

describe('SeasonSelect', () => {
	it('lists "-", Specials and the seasons, with the current one kept', () => {
		const { control } = render({ value: 7, seasons: [2, 1] });
		expect(options(control as HTMLSelectElement)).toEqual([
			['', '-'],
			['0', 'Specials'],
			['1', 'Season 1'],
			['2', 'Season 2'],
			['7', 'Season 7']
		]);
		expect(control.value).toBe('7');
	});

	it('reads "-" when unset and offers Scan all seasons only when allowed', () => {
		const { control } = render({ value: null, seasons: [1], allowScan: true });
		expect(control.value).toBe('');
		expect(options(control as HTMLSelectElement).map(([, t]) => t)).toEqual([
			'-',
			'Scan all seasons',
			'Specials',
			'Season 1'
		]);
	});

	it('maps the select values to a season', async () => {
		const { control, onchange } = render({ value: null, seasons: [1, 2], allowScan: true });
		await fireEvent.change(control, { target: { value: '0' } });
		await fireEvent.change(control, { target: { value: '2' } });
		await fireEvent.change(control, { target: { value: 'scan' } });
		expect(onchange.mock.calls.map((c) => c[0])).toEqual([0, 2, 'scan']);
	});

	it('falls back to a number input when the list is unavailable', async () => {
		const { control, onchange } = render({ value: 3, seasons: null });
		expect(control).toHaveAttribute('type', 'number');
		expect(control.value).toBe('3');
		for (const value of ['4', '', '-1', '1.5']) await fireEvent.input(control, { target: { value } });
		expect(onchange.mock.calls.map((c) => c[0])).toEqual([4, null, null, null]);
	});
});
