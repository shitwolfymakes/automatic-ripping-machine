import { describe, it, expect, afterEach } from 'vitest';
import { createRawSnippet } from 'svelte';
import { renderComponent, screen, cleanup } from '$lib/testing/render';
import FieldLabel from '../FieldLabel.svelte';

const chip = createRawSnippet(() => ({ render: () => '<span>Changed</span>' }));
const unit = createRawSnippet(() => ({ render: () => '<span>(s)</span>' }));

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
		expect(screen.getByRole('link', { name: 'Docs for Rip policy (opens in a new tab)' })).toBeInTheDocument();
	});

	it('passes the fallback id and a resolved link through to the docs link', () => {
		renderComponent(FieldLabel, {
			props: { for: 'a', label: 'Color', docsId: 'handbrake.key.Nope', docsFallbackId: 'handbrake.group.video.Color' }
		});
		expect(screen.getByRole('link', { name: 'Docs for Color (opens in a new tab)' })).toHaveAttribute(
			'href',
			'https://handbrake.fr/docs/en/latest/technical/hdr.html'
		);
		cleanup();
		renderComponent(FieldLabel, {
			props: { for: 'a', label: 'X', docsId: 'x', docsLink: { type: 'external', url: 'https://example.test/x' } }
		});
		expect(screen.getByRole('link', { name: 'Docs for X (opens in a new tab)' })).toHaveAttribute(
			'href',
			'https://example.test/x'
		);
	});

	it('shows no docs link without a docs id', () => {
		renderComponent(FieldLabel, { props: { for: 'a', label: 'A' } });
		expect(screen.queryByRole('link')).toBeNull();
	});

	it('renders the trailing snippet after the label', () => {
		renderComponent(FieldLabel, { props: { for: 'a', label: 'A', children: chip } });
		expect(screen.getByText('Changed')).toBeInTheDocument();
	});

	it('names a field with no single control in a plain caption, still with its docs link', () => {
		const { container } = renderComponent(FieldLabel, {
			props: { label: 'Movie sources', docsId: 'config.auto_rip_on_insert' }
		});
		expect(container.querySelector('label')).toBeNull();
		expect(container.querySelector('span.field-label')).toHaveTextContent('Movie sources');
		expect(screen.getByRole('link', { name: 'Docs for Movie sources (opens in a new tab)' })).toBeInTheDocument();
	});

	it('passes a docs title through to the docs link', () => {
		renderComponent(FieldLabel, {
			props: { for: 'a', label: 'Width', docsId: 'handbrake.group.dimensions.Size', docsTitle: 'HandBrake key: W' }
		});
		expect(screen.getByRole('link', { name: 'Docs for Width (opens in a new tab)' })).toHaveAttribute(
			'title',
			'HandBrake key: W'
		);
	});

	it('puts a required "*" and the marks between the label and the "i", outside both names', () => {
		const { container } = renderComponent(FieldLabel, {
			props: {
				for: 'a',
				label: 'Timeout',
				docsId: 'config.auto_rip_on_insert',
				required: true,
				marks: unit,
				children: chip
			}
		});
		const row = container.querySelector('.field-label-row') as HTMLElement;
		const order = Array.from(row.children).map((el) => el.textContent?.trim() || el.tagName);
		expect(order).toEqual(['Timeout', '*', '(s)', 'A', 'Changed']);
		expect(row.querySelector('.field-label-required')).toHaveAttribute('aria-hidden', 'true');
		expect(container.querySelector('label')).toHaveTextContent(/^Timeout$/);
		expect(screen.getByRole('link', { name: 'Docs for Timeout (opens in a new tab)' })).toBeInTheDocument();
	});

	it('shows no "*" for a field that is not required', () => {
		const { container } = renderComponent(FieldLabel, { props: { for: 'a', label: 'A' } });
		expect(container.querySelector('.field-label-required')).toBeNull();
	});
});
