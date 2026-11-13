import { describe, it, expect, afterEach } from 'vitest';
import { renderComponent, screen, cleanup, within } from '$lib/test-utils';
import { createRawSnippet } from 'svelte';
import HealthItem from '../HealthItem.svelte';

function textSnippet(text: string) {
	return createRawSnippet(() => ({ render: () => `<span>${text}</span>` }));
}

function baseProps() {
	return {
		testid: 'card',
		status: 'warning',
		name: 'Raw',
		description: 'Where rips land',
		badge: textSnippet('BADGE'),
		chips: textSnippet('CHIPS')
	};
}

describe('HealthItem', () => {
	afterEach(() => cleanup());

	it('shows the test id, status, name and description', () => {
		renderComponent(HealthItem, { props: baseProps() });
		const card = screen.getByTestId('card');
		expect(card).toHaveAttribute('data-status', 'warning');
		expect(within(card).getByText('Raw')).toBeInTheDocument();
		expect(within(card).getByText('Where rips land')).toBeInTheDocument();
	});

	it('shows the path when given', () => {
		renderComponent(HealthItem, { props: { ...baseProps(), path: '/data/raw' } });
		expect(screen.getByText('/data/raw')).toBeInTheDocument();
	});

	it('shows no path when none is given', () => {
		renderComponent(HealthItem, { props: baseProps() });
		expect(screen.queryByText('/data/raw')).toBeNull();
		expect(screen.getByTestId('card').querySelector('code')).toBeNull();
	});

	it('renders the badge, chips and footer the caller passes in', () => {
		renderComponent(HealthItem, { props: { ...baseProps(), children: textSnippet('FOOTER') } });
		expect(screen.getByText('BADGE')).toBeInTheDocument();
		expect(screen.getByText('CHIPS')).toBeInTheDocument();
		expect(screen.getByText('FOOTER')).toBeInTheDocument();
	});

	it('renders no footer when none is passed', () => {
		renderComponent(HealthItem, { props: baseProps() });
		expect(screen.queryByText('FOOTER')).toBeNull();
		expect(screen.getByText('CHIPS')).toBeInTheDocument();
	});
});
