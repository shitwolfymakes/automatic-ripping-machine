import { describe, it, expect, afterEach } from 'vitest';
import { renderComponent, screen, cleanup, within } from '$lib/test-utils';
import type { DriveView } from '$lib/types/api.gen';
import FirstDiscCard from '../FirstDiscCard.svelte';

const drive = (over: Partial<DriveView> = {}): DriveView =>
	({
		id: 'drv_a',
		lifecycle: 'enrolled',
		kind: 'optical',
		device_path: '/dev/sr0',
		display_name: 'Front drive',
		present: true,
		status: 'online',
		media_status: 'no_disc',
		...over
	}) as DriveView;

afterEach(cleanup);

describe('FirstDiscCard', () => {
	it('links to the drives step when there is no drive to watch', () => {
		renderComponent(FirstDiscCard, { props: { target: null, ripStarted: false } });

		expect(screen.getByRole('heading', { name: 'Insert a disc to try it' })).toBeInTheDocument();
		expect(screen.getByRole('link', { name: 'Enroll a drive to try it.' })).toHaveAttribute('href', '/setup/drives');
		expect(screen.getByText(/Put any DVD, Blu-ray or CD in the drive/)).toBeInTheDocument();
	});

	it('says it is waiting for a disc while the tray is empty', () => {
		renderComponent(FirstDiscCard, { props: { target: drive(), ripStarted: false } });

		expect(within(screen.getByRole('status')).getByText(/Waiting for a disc in Front drive\.\.\./)).toBeInTheDocument();
	});

	it('says a disc was detected once one is loaded', () => {
		renderComponent(FirstDiscCard, { props: { target: drive({ media_status: 'loaded' }), ripStarted: false } });

		expect(within(screen.getByRole('status')).getByText(/Disc detected in Front drive/)).toBeInTheDocument();
	});

	it('says ripping started once the rip has begun', () => {
		renderComponent(FirstDiscCard, { props: { target: drive({ media_status: 'loaded' }), ripStarted: true } });

		expect(within(screen.getByRole('status')).getByText(/Ripping started in Front drive/)).toBeInTheDocument();
	});
});
