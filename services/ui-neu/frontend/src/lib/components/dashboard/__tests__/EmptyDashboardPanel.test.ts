import { describe, it, expect, afterEach } from 'vitest';
import { renderComponent, screen, cleanup } from '$lib/testing/render';
import EmptyDashboardPanel from '../EmptyDashboardPanel.svelte';
import { setTranscoderEnabled } from '$lib/stores/config';

describe('EmptyDashboardPanel', () => {
	afterEach(() => {
		cleanup();
		setTranscoderEnabled(true);
	});

	it('renders the no-rips-or-transcodes message', () => {
		renderComponent(EmptyDashboardPanel, {
			props: { drivesOnline: 1, armOnline: true, transcoderOnline: true }
		});
		expect(screen.getByText('No active rips or transcodes')).toBeInTheDocument();
	});

	it('leaves transcodes and the transcoder out while the transcoder is disabled', () => {
		setTranscoderEnabled(false);
		renderComponent(EmptyDashboardPanel, {
			props: { drivesOnline: 1, armOnline: true, transcoderOnline: false }
		});
		expect(screen.getByText('No active rips')).toBeInTheDocument();
		expect(screen.queryByText(/transcoder offline/)).toBeNull();
	});

	it('pluralizes drive count correctly', () => {
		renderComponent(EmptyDashboardPanel, {
			props: { drivesOnline: 2, armOnline: true, transcoderOnline: true }
		});
		expect(screen.getByText(/2 drives online/)).toBeInTheDocument();
	});

	it('uses singular for one drive', () => {
		renderComponent(EmptyDashboardPanel, {
			props: { drivesOnline: 1, armOnline: true, transcoderOnline: true }
		});
		expect(screen.getByText(/1 drive online/)).toBeInTheDocument();
	});

	it('reads the plural with a blank count while the drive count is unknown', () => {
		renderComponent(EmptyDashboardPanel, {
			props: { drivesOnline: null, armOnline: true, transcoderOnline: true }
		});
		expect(screen.getByText(/Insert a disc to get started -\s+drives online/)).toBeInTheDocument();
	});

	it('surfaces ARM offline state', () => {
		renderComponent(EmptyDashboardPanel, {
			props: { drivesOnline: 1, armOnline: false, transcoderOnline: true }
		});
		expect(screen.getByText(/ARM offline/)).toBeInTheDocument();
	});

	it('surfaces transcoder offline state', () => {
		renderComponent(EmptyDashboardPanel, {
			props: { drivesOnline: 1, armOnline: true, transcoderOnline: false }
		});
		expect(screen.getByText(/transcoder offline/)).toBeInTheDocument();
	});
});
