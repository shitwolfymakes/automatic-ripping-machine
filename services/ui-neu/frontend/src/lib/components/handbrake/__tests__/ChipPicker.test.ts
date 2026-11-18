import { describe, it, expect, vi, afterEach } from 'vitest';
import { renderComponent, screen, cleanup } from '$lib/test-utils';
import { fireEvent } from '@testing-library/svelte';
import ChipPicker from '../ChipPicker.svelte';

function mount(over: Record<string, unknown> = {}) {
	const onchange = vi.fn();
	renderComponent(ChipPicker, { props: { id: 'c', values: ['a', 'b'], options: null, onchange, ...over } });
	return onchange;
}
const box = () => screen.getByLabelText('Add value') as HTMLInputElement;

describe('ChipPicker', () => {
	afterEach(() => cleanup());

	it('adds a trimmed value with Enter and clears the input', async () => {
		const onchange = mount();
		await fireEvent.input(box(), { target: { value: '  c ' } });
		await fireEvent.keyDown(box(), { key: 'Enter' });
		expect(onchange).toHaveBeenCalledWith(['a', 'b', 'c']);
		expect(box().value).toBe('');
	});

	it('ignores other keys, empties and duplicates', async () => {
		const onchange = mount();
		await fireEvent.input(box(), { target: { value: 'z' } });
		await fireEvent.keyDown(box(), { key: 'a' });
		await fireEvent.click(screen.getByRole('button', { name: 'Add' }));
		await fireEvent.click(screen.getByRole('button', { name: 'Add' }));
		await fireEvent.input(box(), { target: { value: 'a' } });
		await fireEvent.click(screen.getByRole('button', { name: 'Add' }));
		expect(onchange).toHaveBeenCalledTimes(1);
		expect(onchange).toHaveBeenCalledWith(['a', 'b', 'z']);
	});

	it('removes a chip', async () => {
		const onchange = mount();
		await fireEvent.click(screen.getByRole('button', { name: 'Remove a' }));
		expect(onchange).toHaveBeenCalledWith(['b']);
	});

	it('picks from options not already chosen', async () => {
		const onchange = mount({ options: ['a', 'x', 3] });
		const select = screen.getByLabelText('Add value') as HTMLSelectElement;
		expect([...select.options].map((o) => o.value)).toEqual(['', 'x', '3']);
		await fireEvent.change(select, { target: { value: '3' } });
		expect(onchange).toHaveBeenCalledWith(['a', 'b', '3']);
	});

	it('disables its controls', () => {
		mount({ disabled: true });
		expect(box()).toBeDisabled();
		expect(screen.getByRole('button', { name: 'Remove a' })).toBeDisabled();
	});

	it('searches choices by label, code or name and shows chip labels', async () => {
		const choices = [
			{ value: 'eng', label: 'English (eng)' },
			{ value: 'fre', label: 'French (fre)' }
		];
		const onchange = mount({ values: ['fre', 'xx'], choices });
		expect(screen.getByText('French (fre)')).toBeInTheDocument();
		expect(screen.getByText('xx')).toBeInTheDocument();
		const listed = [...document.querySelectorAll('datalist option')].map((o) => (o as HTMLOptionElement).value);
		expect(listed).toEqual(['English (eng)']);
		await fireEvent.input(box(), { target: { value: 'english' } });
		await fireEvent.keyDown(box(), { key: 'Enter' });
		expect(onchange).toHaveBeenLastCalledWith(['fre', 'xx', 'eng']);
	});

	it('keeps unmatched text with a message until typing resumes', async () => {
		const onchange = mount({ choices: [{ value: 'eng', label: 'English (eng)' }] });
		await fireEvent.input(box(), { target: { value: 'klingon' } });
		await fireEvent.click(screen.getByRole('button', { name: 'Add' }));
		expect(screen.getByRole('status')).toHaveTextContent('No matching language');
		expect(box().value).toBe('klingon');
		expect(onchange).not.toHaveBeenCalled();
		await fireEvent.input(box(), { target: { value: 'kling' } });
		expect(screen.queryByRole('status')).toBeNull();
	});

	it('adds a picked suggestion at once, and a stored B code is not added twice', async () => {
		const choices = [{ value: 'fra', label: 'French (fra)', alias: 'fre' }];
		const onchange = mount({ values: ['fre'], choices });
		expect(screen.getByText('French (fra)')).toBeInTheDocument();
		await fireEvent.input(box(), { target: { value: 'French (fra)' } });
		expect(onchange).not.toHaveBeenCalled();
		expect(box().value).toBe('');
	});

	it('adds an exactly picked suggestion without Enter or Add', async () => {
		const onchange = mount({ values: [], choices: [{ value: 'eng', label: 'English (eng)' }] });
		await fireEvent.input(box(), { target: { value: 'Engl' } });
		expect(onchange).not.toHaveBeenCalled();
		await fireEvent.input(box(), { target: { value: 'English (eng)' } });
		expect(onchange).toHaveBeenCalledWith(['eng']);
	});
});
