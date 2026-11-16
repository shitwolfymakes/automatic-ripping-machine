import { describe, it, expect, afterEach, vi } from 'vitest';
import { renderComponent, screen, cleanup, fireEvent } from '$lib/testing/render';
import IdentityCheckbox from '../IdentityCheckbox.svelte';

afterEach(cleanup);

const props = (over: Record<string, unknown> = {}) => ({
	label: 'Use TMDB',
	docsId: 'config.thediscdb_enabled',
	describedby: 'help-id',
	checked: false,
	disabled: false,
	onchange: vi.fn(),
	...over
});

describe('IdentityCheckbox', () => {
	it('names the checkbox by its label', () => {
		renderComponent(IdentityCheckbox, props());
		expect(screen.getByRole('checkbox', { name: 'Use TMDB' })).toBeInTheDocument();
	});

	it('points aria-describedby at the help id', () => {
		renderComponent(IdentityCheckbox, props());
		expect(screen.getByRole('checkbox', { name: 'Use TMDB' })).toHaveAttribute('aria-describedby', 'help-id');
	});

	it('draws the label text beside the checkbox', () => {
		renderComponent(IdentityCheckbox, props());
		expect(screen.getByText('Use TMDB')).toBeInTheDocument();
	});

	it('shows the checked state it is given', () => {
		renderComponent(IdentityCheckbox, props({ checked: true }));
		expect(screen.getByRole('checkbox', { name: 'Use TMDB' })).toBeChecked();
	});

	it('shows an unchecked state', () => {
		renderComponent(IdentityCheckbox, props({ checked: false }));
		expect(screen.getByRole('checkbox', { name: 'Use TMDB' })).not.toBeChecked();
	});

	it('disables the checkbox when told to', () => {
		renderComponent(IdentityCheckbox, props({ disabled: true }));
		expect(screen.getByRole('checkbox', { name: 'Use TMDB' })).toBeDisabled();
	});

	it('leaves the checkbox enabled otherwise', () => {
		renderComponent(IdentityCheckbox, props());
		expect(screen.getByRole('checkbox', { name: 'Use TMDB' })).toBeEnabled();
	});

	it('calls onchange(true) when ticked', async () => {
		const onchange = vi.fn();
		renderComponent(IdentityCheckbox, props({ onchange }));
		await fireEvent.click(screen.getByRole('checkbox', { name: 'Use TMDB' }));
		expect(onchange).toHaveBeenCalledWith(true);
	});

	it('calls onchange(false) when unticked', async () => {
		const onchange = vi.fn();
		renderComponent(IdentityCheckbox, props({ checked: true, onchange }));
		await fireEvent.click(screen.getByRole('checkbox', { name: 'Use TMDB' }));
		expect(onchange).toHaveBeenCalledWith(false);
	});

	it('labels the checkbox through for and links its setting docs beside the label', () => {
		renderComponent(IdentityCheckbox, props());
		const box = screen.getByRole('checkbox', { name: 'Use TMDB' });
		const label = screen.getByText('Use TMDB');
		expect(label).toHaveAttribute('for', box.id);
		const link = screen.getByRole('link', { name: 'Docs for Use TMDB (opens in a new tab)' });
		expect(link).toHaveAttribute('data-field-id', 'config.thediscdb_enabled');
		expect(label).not.toContainElement(link);
	});

	it('shows no docs link for a setting without a registry entry', () => {
		renderComponent(IdentityCheckbox, props({ docsId: 'config.NOT_A_FIELD' }));
		expect(screen.queryByRole('link')).toBeNull();
	});
});
