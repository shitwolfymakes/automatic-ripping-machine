import { describe, it, expect, afterEach, vi } from 'vitest';
import { renderComponent, screen, fireEvent, cleanup } from '$lib/testing/render';
import HelpSearchBox from '../HelpSearchBox.svelte';

afterEach(cleanup);

const HITS = [
	{ id: 'a', title: 'Alpha', href: '/help/a' },
	{ id: 'b', title: 'Beta', href: '/help/b' }
];

function renderBox(props: Partial<{ query: string; hits: typeof HITS; onsearch: (v: string) => void }> = {}) {
	return renderComponent(HelpSearchBox, { props: { query: '', hits: [], onsearch: () => {}, ...props } });
}

describe('HelpSearchBox', () => {
	it('shows the query in a labelled search input', () => {
		renderBox({ query: 'rip' });
		const input = screen.getByRole('searchbox', { name: 'Search help' });
		expect(input).toHaveValue('rip');
		expect(input).toHaveAttribute('placeholder', 'Search help');
	});

	it('calls onsearch with the typed value', async () => {
		const onsearch = vi.fn();
		renderBox({ onsearch });
		await fireEvent.input(screen.getByRole('searchbox'), { target: { value: 'disc' } });
		expect(onsearch).toHaveBeenCalledWith('disc');
	});

	it('shows no results panel for an empty query', () => {
		const { container } = renderBox({ query: '', hits: HITS });
		expect(container.querySelector('.help-results')).toBeNull();
	});

	it('shows no results panel for a query of only spaces', () => {
		const { container } = renderBox({ query: '   ', hits: HITS });
		expect(container.querySelector('.help-results')).toBeNull();
	});

	it('lists each hit as a link to its page', () => {
		renderBox({ query: 'a', hits: HITS });
		expect(screen.getByRole('link', { name: 'Alpha' })).toHaveAttribute('href', '/help/a');
		expect(screen.getByRole('link', { name: 'Beta' })).toHaveAttribute('href', '/help/b');
		expect(screen.queryByText('No matches')).not.toBeInTheDocument();
	});

	it('says there are no matches when a query has no hits', () => {
		renderBox({ query: 'zzz', hits: [] });
		expect(screen.getByText('No matches')).toBeInTheDocument();
	});
});
