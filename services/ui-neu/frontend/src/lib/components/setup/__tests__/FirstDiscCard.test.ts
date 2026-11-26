import { describe, it, expect, afterEach, beforeEach, vi } from 'vitest';
import { renderComponent, screen, cleanup, within, waitFor } from '$lib/testing/render';
import type { DriveView } from '$lib/types/api.gen';
import type { WSEnvelope } from '$lib/api/ws';
import FirstDiscCard from '../FirstDiscCard.svelte';

type Handler = (env: WSEnvelope) => void;

const ws = vi.hoisted(() => ({
	handler: null as ((env: unknown) => void) | null,
	unsubscribe: undefined as (() => void) | undefined,
	start: undefined as (() => void) | undefined,
	subscribe: undefined as ((topic: string, h: (env: unknown) => void) => (() => void) | undefined) | undefined
}));
vi.mock('$lib/api/ws', () => ({
	wsClient: {
		start: () => ws.start?.(),
		subscribe: (topic: string, h: (env: unknown) => void) => ws.subscribe?.(topic, h)
	}
}));

const emit = (env: Partial<WSEnvelope>) =>
	(ws.handler as Handler)({ event_type: 'rip.started', payload: {}, ...env } as WSEnvelope);

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

beforeEach(() => {
	ws.handler = null;
	ws.unsubscribe = vi.fn();
	ws.start = vi.fn();
	ws.subscribe = vi.fn((_topic, h) => {
		ws.handler = h;
		return ws.unsubscribe;
	});
});

afterEach(() => {
	cleanup();
	vi.clearAllMocks();
});

describe('FirstDiscCard', () => {
	it('links to the drives step when there is no drive to watch', () => {
		renderComponent(FirstDiscCard, { props: { target: null } });

		expect(screen.getByRole('heading', { name: 'Insert a disc to try it' })).toBeInTheDocument();
		expect(screen.getByRole('link', { name: 'Enroll a drive to try it.' })).toHaveAttribute('href', '/setup/drives');
		expect(screen.getByText(/Put any DVD, Blu-ray or CD in the drive/)).toBeInTheDocument();
	});

	it('says it is waiting for a disc while the tray is empty', () => {
		renderComponent(FirstDiscCard, { props: { target: drive() } });

		expect(within(screen.getByRole('status')).getByText(/Waiting for a disc in Front drive\.\.\./)).toBeInTheDocument();
	});

	it('says a disc was detected once one is loaded', () => {
		renderComponent(FirstDiscCard, { props: { target: drive({ media_status: 'loaded' }) } });

		expect(within(screen.getByRole('status')).getByText(/Disc detected in Front drive/)).toBeInTheDocument();
	});

	it('says ripping started once a rip.started event arrives for the target', async () => {
		renderComponent(FirstDiscCard, { props: { target: drive({ media_status: 'loaded' }) } });

		emit({ payload: { drive_id: 'drv_a' } });

		await waitFor(() =>
			expect(within(screen.getByRole('status')).getByText(/Ripping started in Front drive/)).toBeInTheDocument()
		);
	});

	it('ignores a rip.started event for another drive', async () => {
		renderComponent(FirstDiscCard, { props: { target: drive({ media_status: 'loaded' }) } });

		emit({ payload: { drive_id: 'drv_b' } });

		await waitFor(() =>
			expect(within(screen.getByRole('status')).getByText(/Disc detected in Front drive/)).toBeInTheDocument()
		);
	});

	it('ignores an event of another type', async () => {
		renderComponent(FirstDiscCard, { props: { target: drive({ media_status: 'loaded' }) } });

		emit({ event_type: 'rip.finished', payload: { drive_id: 'drv_a' } });

		await waitFor(() =>
			expect(within(screen.getByRole('status')).getByText(/Disc detected in Front drive/)).toBeInTheDocument()
		);
	});

	it('ignores a rip.started event when there is no target', async () => {
		renderComponent(FirstDiscCard, { props: { target: null } });

		emit({ payload: { drive_id: 'drv_a' } });

		await waitFor(() => expect(screen.getByRole('link', { name: 'Enroll a drive to try it.' })).toBeInTheDocument());
	});

	it('starts the socket and subscribes to ripper.events', () => {
		renderComponent(FirstDiscCard, { props: { target: drive() } });

		expect(ws.start).toHaveBeenCalledTimes(1);
		expect(ws.subscribe).toHaveBeenCalledWith('ripper.events', expect.any(Function));
	});

	it('unsubscribes when unmounted', () => {
		const { unmount } = renderComponent(FirstDiscCard, { props: { target: drive() } });

		unmount();

		expect(ws.unsubscribe).toHaveBeenCalledTimes(1);
	});

	it('unmounts without error when subscribe returns nothing', () => {
		ws.subscribe = vi.fn(() => undefined);
		const { unmount } = renderComponent(FirstDiscCard, { props: { target: drive() } });

		expect(() => unmount()).not.toThrow();
	});
});
