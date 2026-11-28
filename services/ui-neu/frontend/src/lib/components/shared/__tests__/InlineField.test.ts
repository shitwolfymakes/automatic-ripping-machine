// Open arms the coverage tool reports that are Svelte's, not the component's:
// each attribute `{...}` below compiles to `(...) ?? ''`, and none can be
// nullish. The class prop in the input's class list (defaulting to '') and
// the label in the button's `Edit {label}` name (a required string).
import { describe, it, expect, vi, afterEach } from 'vitest';
import { renderComponent, screen, cleanup, fireEvent, waitFor } from '$lib/testing/render';
import InlineField from '../InlineField.svelte';

type Props = {
	label?: string;
	value?: string | null;
	type?: 'text' | 'number';
	canEdit?: boolean;
	class?: string;
	onsave?: (raw: string) => Promise<void> | void;
};

function render(props: Props = {}) {
	const onsave = props.onsave ?? vi.fn();
	renderComponent(InlineField, { label: 'Album', value: 'Two Windows', canEdit: true, ...props, onsave });
	return { onsave };
}

const openEditor = async () => {
	await fireEvent.click(screen.getByRole('button', { name: 'Edit Album' }));
	return screen.getByRole('textbox', { name: 'Album' }) as HTMLInputElement;
};

afterEach(cleanup);

describe('InlineField', () => {
	it('shows the value as plain text when it cannot be edited', () => {
		render({ canEdit: false, class: 'x' });
		expect(screen.getByText('Two Windows')).toHaveClass('x');
		expect(screen.queryByRole('button')).not.toBeInTheDocument();
	});

	it.each([null, ''])('shows a dash for an empty value (%j)', (value) => {
		render({ value });
		expect(screen.getByRole('button', { name: 'Edit Album' })).toHaveTextContent('-');
	});

	it('opens on click with the value as the draft, focused, and saves the typed text on Enter', async () => {
		const { onsave } = render();
		const input = await openEditor();
		expect(input.value).toBe('Two Windows');
		await waitFor(() => expect(input).toHaveFocus());
		await fireEvent.input(input, { target: { value: 'Three Doors' } });
		await fireEvent.keyDown(input, { key: 'Enter' });
		await waitFor(() => expect(onsave).toHaveBeenCalledWith('Three Doors'));
		expect(screen.queryByRole('textbox')).not.toBeInTheDocument();
	});

	it('opens a null value with an empty draft', async () => {
		render({ value: null });
		expect((await openEditor()).value).toBe('');
	});

	it('saves when the field loses focus', async () => {
		const { onsave } = render();
		const input = await openEditor();
		await fireEvent.input(input, { target: { value: 'Three Doors' } });
		await fireEvent.blur(input);
		await waitFor(() => expect(onsave).toHaveBeenCalledWith('Three Doors'));
	});

	it.each([
		['the value', 'Two Windows'],
		['a null value, left blank', null]
	])('closes without saving when the draft still equals %s', async (_label, value) => {
		const { onsave } = render({ value });
		const input = await openEditor();
		await fireEvent.keyDown(input, { key: 'Enter' });
		expect(screen.queryByRole('textbox')).not.toBeInTheDocument();
		expect(onsave).not.toHaveBeenCalled();
	});

	it('hands a cleared number field to the owner as blank text', async () => {
		const { onsave } = render({ label: 'Year', value: '2017', type: 'number' });
		await fireEvent.click(screen.getByRole('button', { name: 'Edit Year' }));
		const input = screen.getByRole('spinbutton', { name: 'Year' });
		await fireEvent.input(input, { target: { value: '' } });
		await fireEvent.keyDown(input, { key: 'Enter' });
		await waitFor(() => expect(onsave).toHaveBeenCalledWith(''));
	});

	it('ignores a second save while one is in flight, with the input disabled', async () => {
		let finish: () => void = () => {};
		const { onsave } = render({ onsave: vi.fn(() => new Promise<void>((r) => (finish = r))) });
		const input = await openEditor();
		await fireEvent.input(input, { target: { value: 'Three Doors' } });
		await fireEvent.keyDown(input, { key: 'Enter' });
		await waitFor(() => expect(input).toBeDisabled());
		await fireEvent.blur(input);
		expect(onsave).toHaveBeenCalledTimes(1);
		finish();
		await waitFor(() => expect(screen.queryByRole('textbox')).not.toBeInTheDocument());
	});

	it('ignores a blur that arrives after the editor closed', async () => {
		const { onsave } = render();
		const input = await openEditor();
		await fireEvent.input(input, { target: { value: 'Three Doors' } });
		await fireEvent.keyDown(input, { key: 'Escape' });
		expect(screen.queryByRole('textbox')).not.toBeInTheDocument();
		await fireEvent.blur(input);
		expect(onsave).not.toHaveBeenCalled();
	});

	it('keeps the editor open with the error when the save fails, and clears it on reopen', async () => {
		render({ onsave: vi.fn().mockRejectedValue(new Error('An album is required')) });
		const input = await openEditor();
		await fireEvent.input(input, { target: { value: ' ' } });
		await fireEvent.keyDown(input, { key: 'Enter' });
		expect(await screen.findByText('An album is required')).toBeInTheDocument();
		expect(input).not.toBeDisabled();
		await fireEvent.keyDown(input, { key: 'Escape' });
		await openEditor();
		expect(screen.queryByText('An album is required')).not.toBeInTheDocument();
	});

	it('does nothing on another key', async () => {
		const { onsave } = render();
		const input = await openEditor();
		await fireEvent.keyDown(input, { key: 'a' });
		expect(screen.getByRole('textbox', { name: 'Album' })).toBeInTheDocument();
		expect(onsave).not.toHaveBeenCalled();
	});
});
