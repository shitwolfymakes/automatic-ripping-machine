import { describe, it, expect, afterEach } from 'vitest';
import { renderComponent, screen, cleanup, fireEvent } from '$lib/testing/render';
import IdentifyCdFormHarness from './IdentifyCdFormHarness.svelte';

afterEach(() => cleanup());

type Values = { album: string; year: number | null; artist: string; trackTitles: string[] };

const render = (props: { scanTrackCount: number; submitting?: boolean }) => {
	const { component } = renderComponent(IdentifyCdFormHarness, { props });
	return (component as unknown as { getValues: () => Values }).getValues;
};

describe('IdentifyCdForm', () => {
	it('writes typed Album, Year and Artist back to the bound values', async () => {
		const getValues = render({ scanTrackCount: 0 });
		await fireEvent.input(screen.getByTestId('identify-album'), { target: { value: 'Kind of Blue' } });
		await fireEvent.input(screen.getByTestId('identify-year'), { target: { value: '1959' } });
		await fireEvent.input(screen.getByTestId('identify-artist'), { target: { value: 'Miles Davis' } });
		expect(getValues()).toMatchObject({ album: 'Kind of Blue', year: 1959, artist: 'Miles Davis' });
	});

	it('writes a typed track title into that entry of trackTitles', async () => {
		const getValues = render({ scanTrackCount: 3 });
		await fireEvent.input(screen.getByTestId('identify-track-2'), { target: { value: 'Freddie Freeloader' } });
		expect(getValues().trackTitles).toEqual(['', 'Freddie Freeloader', '']);
	});

	it('renders one labelled track input per scanned title', () => {
		render({ scanTrackCount: 3 });
		for (const n of [1, 2, 3]) expect(screen.getByTestId(`identify-track-${n}`)).toBeInTheDocument();
		expect(screen.queryByTestId('identify-track-4')).not.toBeInTheDocument();
		expect(screen.getByText('01')).toBeInTheDocument();
		expect(screen.getByText('02')).toBeInTheDocument();
		expect(screen.getByText('03')).toBeInTheDocument();
	});

	it('shows the helper line and no track inputs when the track count is unknown', () => {
		render({ scanTrackCount: 0 });
		expect(screen.getByText(/Track count couldn't be determined/)).toBeInTheDocument();
		expect(screen.queryByTestId('identify-track-1')).not.toBeInTheDocument();
	});

	it('disables every input while submitting', () => {
		render({ scanTrackCount: 2, submitting: true });
		for (const id of ['identify-album', 'identify-year', 'identify-artist', 'identify-track-1', 'identify-track-2']) {
			expect(screen.getByTestId(id)).toBeDisabled();
		}
	});
});
