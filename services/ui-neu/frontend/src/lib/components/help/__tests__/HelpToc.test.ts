import { describe, it, expect, afterEach } from 'vitest';
import { renderComponent, screen, within, cleanup } from '$lib/testing/render';
import type { DocsTocEntry } from '$lib/help/api';
import HelpToc from '../HelpToc.svelte';

afterEach(cleanup);

const TOC: DocsTocEntry[] = [
	{ depth: 2, id: 'install', text: 'Install' },
	{ depth: 3, id: 'docker', text: 'With Docker' },
	{ depth: 2, id: 'rip', text: 'Rip a disc' }
];

describe('HelpToc', () => {
	it('labels the nav "On this page" and shows the eyebrow', () => {
		renderComponent(HelpToc, { props: { toc: TOC } });
		const nav = screen.getByRole('navigation', { name: 'On this page' });
		expect(nav.getAttribute('aria-label')).toBe('On this page');
		expect(within(nav).getByText('On this page').className).toContain('eyebrow');
	});

	it('renders one link per entry with its text, fragment href and depth', () => {
		renderComponent(HelpToc, { props: { toc: TOC } });
		const links = screen.getAllByRole('link');
		expect(links.map((a) => a.textContent)).toEqual(['Install', 'With Docker', 'Rip a disc']);
		expect(links.map((a) => a.getAttribute('href'))).toEqual(['#install', '#docker', '#rip']);
		expect(links.map((a) => a.getAttribute('data-depth'))).toEqual(['2', '3', '2']);
	});

	it('renders no links for an empty toc', () => {
		renderComponent(HelpToc, { props: { toc: [] } });
		expect(screen.queryAllByRole('link')).toEqual([]);
	});
});
