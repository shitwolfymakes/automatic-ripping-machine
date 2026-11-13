import { describe, it, expect, afterEach } from 'vitest';
import { renderComponent, screen, cleanup } from '$lib/test-utils';
import type { IsoStatus } from '$lib/drives/setup-drives';
import IsoLibraryCard from '../IsoLibraryCard.svelte';

function renderCard(iso: IsoStatus) {
	return renderComponent(IsoLibraryCard, { props: { iso } });
}

describe('IsoLibraryCard', () => {
	afterEach(() => cleanup());

	it('shows a singular image count when the library is on with one image', () => {
		renderCard({ on: true, count: 1, path: null });
		expect(screen.getByTestId('drives-iso')).toHaveTextContent('ISO library: on, 1 image');
		expect(screen.getByTestId('drives-iso')).not.toHaveTextContent('1 images');
	});

	it('shows a plural image count when the library is on with two images', () => {
		renderCard({ on: true, count: 2, path: null });
		expect(screen.getByTestId('drives-iso')).toHaveTextContent('ISO library: on, 2 images');
	});

	it('shows the images path when the library is on with a path', () => {
		renderCard({ on: true, count: 2, path: '/mnt/isos' });
		expect(screen.getByText('/mnt/isos')).toBeInTheDocument();
		expect(screen.getByText(/Images are read from/)).toBeInTheDocument();
	});

	it('shows no path line when the library is on without a path', () => {
		renderCard({ on: true, count: 2, path: null });
		expect(screen.queryByText(/Images are read from/)).not.toBeInTheDocument();
		expect(screen.queryByText(/To turn it on/)).not.toBeInTheDocument();
	});

	it('shows the .env line to add and the help link when the library is off', () => {
		renderCard({ on: false, count: 0, path: null });
		expect(screen.getByTestId('drives-iso')).toHaveTextContent('ISO library: off');
		expect(screen.getByText(/To turn it on/)).toBeInTheDocument();
		expect(screen.getByText('ARM_HOST_ISO_LIBRARY_PATH=/path/to/your/isos')).toBeInTheDocument();
		expect(screen.getByRole('link', { name: 'Read how' })).toHaveAttribute('href', '/help');
	});
});
