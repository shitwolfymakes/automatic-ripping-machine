import { describe, it, expect, afterEach } from 'vitest';
import { createRawSnippet } from 'svelte';
import { renderComponent, screen, cleanup } from '$lib/testing/render';
import FieldLabel from '../FieldLabel.svelte';

const chip = createRawSnippet(() => ({ render: () => '<span>Changed</span>' }));

describe('FieldLabel', () => {
	afterEach(() => cleanup());

	it('labels its control through for', () => {
		const { container } = renderComponent(FieldLabel, { props: { for: 'f-width', label: 'Width' } });
		const label = container.querySelector('label');
		expect(label).toHaveAttribute('for', 'f-width');
		expect(label).toHaveTextContent('Width');
		expect(label).toHaveClass('field-label');
	});

	it('shows the docs link for its docs id, named after the label', () => {
		renderComponent(FieldLabel, { props: { for: 'a', label: 'Rip policy', docsId: 'config.auto_rip_on_insert' } });
		expect(screen.getByRole('link', { name: 'Docs for Rip policy' })).toBeInTheDocument();
	});

	it('passes the fallback id and a resolved link through to the docs link', () => {
		renderComponent(FieldLabel, {
			props: { for: 'a', label: 'Color', docsId: 'handbrake.key.Nope', docsFallbackId: 'handbrake.group.video.Color' }
		});
		expect(screen.getByRole('link', { name: 'Docs for Color' })).toHaveAttribute(
			'href',
			'https://handbrake.fr/docs/en/latest/technical/hdr.html'
		);
		cleanup();
		renderComponent(FieldLabel, {
			props: { for: 'a', label: 'X', docsId: 'x', docsLink: { type: 'external', url: 'https://example.test/x' } }
		});
		expect(screen.getByRole('link', { name: 'Docs for X' })).toHaveAttribute('href', 'https://example.test/x');
	});

	it('shows no docs link without a docs id', () => {
		renderComponent(FieldLabel, { props: { for: 'a', label: 'A' } });
		expect(screen.queryByRole('link')).toBeNull();
	});

	it('renders the trailing snippet after the label', () => {
		renderComponent(FieldLabel, { props: { for: 'a', label: 'A', children: chip } });
		expect(screen.getByText('Changed')).toBeInTheDocument();
	});
});
