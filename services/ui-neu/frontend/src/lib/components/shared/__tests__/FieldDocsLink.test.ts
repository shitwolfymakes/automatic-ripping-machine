import { describe, it, expect, afterEach } from 'vitest';
import { renderComponent, screen, cleanup } from '$lib/testing/render';
import FieldDocsLink from '../FieldDocsLink.svelte';

describe('FieldDocsLink', () => {
	afterEach(() => cleanup());

	it('opens an external link in a new tab without opener access', () => {
		renderComponent(FieldDocsLink, { props: { id: 'handbrake.group.dimensions.Size', label: 'Width' } });
		const link = screen.getByRole('link', { name: 'Docs for Width' });
		expect(link).toHaveAttribute('href', 'https://handbrake.fr/docs/en/latest/advanced/resizing-video.html');
		expect(link).toHaveAttribute('target', '_blank');
		expect(link).toHaveAttribute('rel', 'noopener noreferrer');
		expect(link).toHaveAttribute('title', 'Open the documentation');
	});

	it('opens an internal link in the same tab at its help anchor', () => {
		renderComponent(FieldDocsLink, { props: { id: 'config.auto_rip_on_insert', label: 'Rip policy' } });
		const link = screen.getByRole('link', { name: 'Docs for Rip policy' });
		expect(link).toHaveAttribute('href', '/help/guide/configuring-arm#rip--transcode-behaviour');
		expect(link).not.toHaveAttribute('target');
		expect(link).not.toHaveAttribute('rel');
		expect(link).toHaveAttribute('title', 'Open the ARM help');
	});

	it('renders nothing for an unknown id', () => {
		renderComponent(FieldDocsLink, { props: { id: 'config.NOT_A_FIELD', label: 'X' } });
		expect(screen.queryByRole('link')).toBeNull();
	});

	it('renders nothing for an opt-out', () => {
		renderComponent(FieldDocsLink, { props: { id: 'config.BIND_PORT', label: 'Secret' } });
		expect(screen.queryByRole('link')).toBeNull();
	});

	it('uses the fallback id when the id has no entry', () => {
		renderComponent(FieldDocsLink, {
			props: { id: 'handbrake.key.Nope', fallbackId: 'handbrake.group.video.Color', label: 'Color' }
		});
		expect(screen.getByRole('link', { name: 'Docs for Color' })).toHaveAttribute(
			'href',
			'https://handbrake.fr/docs/en/latest/technical/hdr.html'
		);
	});

	it('shows a link the caller resolved, ignoring the registry', () => {
		renderComponent(FieldDocsLink, {
			props: { id: 'config.NOT_A_FIELD', label: 'X', link: { type: 'external', url: 'https://example.test/x' } }
		});
		expect(screen.getByRole('link', { name: 'Docs for X' })).toHaveAttribute('href', 'https://example.test/x');
	});

	it('renders nothing for a resolved link of null', () => {
		renderComponent(FieldDocsLink, { props: { id: 'handbrake.group.video.Color', label: 'X', link: null } });
		expect(screen.queryByRole('link')).toBeNull();
	});
});
