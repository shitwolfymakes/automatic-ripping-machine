import { describe, it, expect, vi, afterEach } from 'vitest';
import { renderComponent, screen, fireEvent, cleanup } from '$lib/test-utils';
import AutoSaveSelect from '../AutoSaveSelect.svelte';

afterEach(cleanup);

const PROPS = {
	key: 'miss_media_type',
	label: 'Treat unidentified video discs as',
	help: 'Starts as this type.',
	options: [
		{ value: 'movie', label: 'movie' },
		{ value: 'tv', label: 'tv' }
	]
};

describe('AutoSaveSelect', () => {
	it('renders the options with the current one selected, plus help, anchor and the auto-save hint', () => {
		renderComponent(AutoSaveSelect, { props: { ...PROPS, value: 'tv', onchange: vi.fn() } });
		const select = screen.getByRole('combobox', { name: PROPS.label });
		expect(select).toHaveValue('tv');
		expect(screen.getAllByRole('option').map((o) => o.textContent)).toEqual(['movie', 'tv']);
		expect(screen.getByText(PROPS.help)).toBeInTheDocument();
		expect(screen.getByText('(changes save automatically)')).toBeInTheDocument();
		expect(screen.getByTestId('setting-miss_media_type')).toHaveAttribute('id', 'setting-miss_media_type');
		expect(screen.queryByRole('button', { name: 'Save' })).not.toBeInTheDocument();
	});

	it('reports the chosen value', async () => {
		const onchange = vi.fn();
		renderComponent(AutoSaveSelect, { props: { ...PROPS, value: 'movie', onchange } });
		await fireEvent.change(screen.getByRole('combobox', { name: PROPS.label }), { target: { value: 'tv' } });
		expect(onchange).toHaveBeenCalledWith('tv');
	});

	it('leaves out the help line when there is none', () => {
		renderComponent(AutoSaveSelect, { props: { ...PROPS, help: null, value: 'movie', onchange: vi.fn() } });
		expect(screen.getByTestId('setting-miss_media_type').querySelector('.field-help')).toBeNull();
	});
});
