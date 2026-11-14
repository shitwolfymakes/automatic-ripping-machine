import { describe, it, expect, afterEach } from 'vitest';
import { renderComponent, screen, within, cleanup } from '$lib/testing/render';
import IsoLibrarySetup from '../IsoLibrarySetup.svelte';

describe('IsoLibrarySetup', () => {
	afterEach(() => cleanup());

	it('shows the setup title', () => {
		renderComponent(IsoLibrarySetup);
		expect(screen.getByText('Set up your ISO library first')).toBeInTheDocument();
	});

	it('lists the three steps in order', () => {
		renderComponent(IsoLibrarySetup);
		const steps = screen.getAllByRole('listitem');
		expect(steps).toHaveLength(3);
		expect(steps[0].textContent).toContain('ARM_HOST_ISO_LIBRARY_PATH');
		expect(steps[1].textContent).toContain('armctl up');
		expect(steps[2]).toHaveTextContent('Open Rip from ISO again and pick a file.');
	});

	it('shows the library path example', () => {
		renderComponent(IsoLibrarySetup);
		expect(screen.getByText('ARM_HOST_ISO_LIBRARY_PATH=/mnt/nas/iso')).toBeInTheDocument();
	});

	it('shows both commands', () => {
		renderComponent(IsoLibrarySetup);
		const steps = screen.getAllByRole('listitem');
		expect(within(steps[1]).getByText('armctl up')).toBeInTheDocument();
		expect(within(steps[1]).getByText('bash devtools/setup-dev.sh up')).toBeInTheDocument();
	});

	it('ends with the read-only sentence', () => {
		renderComponent(IsoLibrarySetup);
		expect(
			screen.getByText('ARM only reads this folder. It never moves, renames or deletes your ISO files.')
		).toBeInTheDocument();
	});
});
