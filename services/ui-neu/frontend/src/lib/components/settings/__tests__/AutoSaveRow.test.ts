import { describe, it, expect, afterEach } from 'vitest';
import { createRawSnippet } from 'svelte';
import { renderComponent, screen, cleanup } from '$lib/testing/render';
import AutoSaveRow from '../AutoSaveRow.svelte';

// Every branch of the component's own code is covered. The coverage tool still
// reports one open arm that is Svelte's: `id="setting-{key}"` compiles to
// `(...) ?? ''`, and the key is a required string.

afterEach(cleanup);

const control = createRawSnippet(() => ({ render: () => '<input aria-label="Control" />' }));

describe('AutoSaveRow', () => {
	it('renders the control with the setting anchor, the auto-save hint and the help line', () => {
		renderComponent(AutoSaveRow, {
			props: { key: 'miss_media_type', help: 'Starts as this type.', children: control }
		});
		const row = screen.getByTestId('setting-miss_media_type');
		expect(row).toHaveAttribute('id', 'setting-miss_media_type');
		expect(screen.getByRole('textbox', { name: 'Control' })).toBeInTheDocument();
		expect(screen.getByText('(changes save automatically)')).toBeInTheDocument();
		expect(screen.getByText('Starts as this type.')).toHaveClass('field-help');
	});

	it('leaves out the help line when there is none', () => {
		renderComponent(AutoSaveRow, { props: { key: 'miss_media_type', children: control } });
		expect(screen.getByTestId('setting-miss_media_type').querySelector('.field-help')).toBeNull();
	});
});
