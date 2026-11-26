import { describe, it, expect, afterEach } from 'vitest';
import { renderComponent, screen, fireEvent, cleanup } from '$lib/testing/render';
import type { DocsNavSection } from '$lib/help/api';
import HelpTopicsHarness from './HelpTopicsHarness.svelte';

afterEach(cleanup);

const NAV: DocsNavSection[] = [
	{
		id: 'start',
		label: 'Getting started',
		groups: [
			{
				label: 'Basics',
				items: [
					{ label: 'Install', href: '/help/start/install', external: false, pageId: 'start/install' },
					{ label: 'Rip a disc', href: '/help/start/rip', external: false, pageId: 'start/rip' }
				]
			},
			{
				label: null,
				items: [{ label: 'Forum', href: 'https://example.com/forum', external: true, pageId: null }]
			}
		]
	},
	{ id: 'ref', label: 'Reference', groups: [] }
];

function renderTopics(activeId = 'start/rip') {
	return renderComponent(HelpTopicsHarness, { props: { nav: NAV, activeId } });
}

describe('HelpTopics', () => {
	it('shows each section label', () => {
		const { container } = renderTopics();
		const labels = [...container.querySelectorAll('.help-section')].map((e) => e.textContent);
		expect(labels).toEqual(['Getting started', 'Reference']);
	});

	it('shows a group label and renders no group for a null label', () => {
		const { container } = renderTopics();
		const groups = container.querySelectorAll('.help-group');
		expect(groups).toHaveLength(1);
		expect(groups[0]).toHaveTextContent('Basics');
	});

	it('shows each item with its label and href', () => {
		renderTopics();
		expect(screen.getByRole('link', { name: 'Install' })).toHaveAttribute('href', '/help/start/install');
		expect(screen.getByRole('link', { name: 'Rip a disc' })).toHaveAttribute('href', '/help/start/rip');
		expect(screen.getByRole('link', { name: 'Forum' })).toHaveAttribute('href', 'https://example.com/forum');
	});

	it('marks only the active item', () => {
		renderTopics('start/rip');
		const active = screen.getByRole('link', { name: 'Rip a disc' });
		expect(active).toHaveAttribute('data-active', 'true');
		expect(active).toHaveAttribute('aria-current', 'page');
		for (const name of ['Install', 'Forum']) {
			const other = screen.getByRole('link', { name });
			expect(other).not.toHaveAttribute('data-active');
			expect(other).not.toHaveAttribute('aria-current');
		}
	});

	it('opens an external item in a new tab with noopener', () => {
		renderTopics();
		const external = screen.getByRole('link', { name: 'Forum' });
		expect(external).toHaveAttribute('target', '_blank');
		expect(external).toHaveAttribute('rel', 'noopener');
	});

	it('gives an internal item no target or rel', () => {
		renderTopics();
		const internal = screen.getByRole('link', { name: 'Install' });
		expect(internal).not.toHaveAttribute('target');
		expect(internal).not.toHaveAttribute('rel');
	});

	it('flips aria-expanded, data-open and the bound open on each toggle click', async () => {
		const { container } = renderTopics();
		const toggle = screen.getByRole('button', { name: 'Topics' });
		const nav = container.querySelector('#help-topics')!;
		expect(toggle).toHaveAttribute('aria-expanded', 'false');
		expect(nav).toHaveAttribute('data-open', 'false');
		expect(screen.getByTestId('open')).toHaveTextContent('false');

		await fireEvent.click(toggle);
		expect(toggle).toHaveAttribute('aria-expanded', 'true');
		expect(nav).toHaveAttribute('data-open', 'true');
		expect(screen.getByTestId('open')).toHaveTextContent('true');

		await fireEvent.click(toggle);
		expect(toggle).toHaveAttribute('aria-expanded', 'false');
		expect(nav).toHaveAttribute('data-open', 'false');
		expect(screen.getByTestId('open')).toHaveTextContent('false');
	});
});
