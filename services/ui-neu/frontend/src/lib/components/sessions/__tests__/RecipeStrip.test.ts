import { describe, it, expect, afterEach } from 'vitest';
import { renderComponent, screen, cleanup } from '$lib/test-utils';
import RecipeStrip from '../RecipeStrip.svelte';

describe('RecipeStrip', () => {
	afterEach(() => cleanup());

	it('renders each cell with chevron-icon separators, never a > character', () => {
		const { container } = renderComponent(RecipeStrip, {
			props: {
				cells: [
					{ label: 'Rips', value: 'Main feature', sub: 'Longest title' },
					{ label: 'Encodes', value: null, empty: 'No encode' },
					{ label: 'Lands in', value: '/media/Movies/Title (Year)/', mono: true }
				]
			}
		});
		expect(screen.getByText('Main feature')).toBeInTheDocument();
		expect(screen.getByText('Longest title')).toBeInTheDocument();
		expect(screen.getByText('No encode')).toBeInTheDocument();
		expect(screen.getByText('/media/Movies/Title (Year)/')).toHaveClass('mono');
		expect(container.querySelectorAll('.recipe-strip-arrow svg')).toHaveLength(2);
		expect(container.textContent).not.toContain('>');
	});
});
