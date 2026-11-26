import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderComponent, screen, cleanup, waitFor, within } from '$lib/testing/render';
import type { ConfigView, DriveView, GpuView, NotificationChannelView, SetupView } from '$lib/types/api.gen';
import type { WSEnvelope } from '$lib/api/ws';

// Pins what FinishStep does today. Only the I/O boundary is faked: the api
// modules, the WebSocket client and the transcoder flag. No branch is left
// open.

const fetchDrives = vi.fn();
vi.mock('$lib/api/drives', () => ({ fetchDrives: () => fetchDrives() }));
const fetchConfigView = vi.fn();
vi.mock('$lib/api/config', () => ({ fetchConfigView: () => fetchConfigView() }));
const fetchGpus = vi.fn();
vi.mock('$lib/api/gpus', () => ({ fetchGpus: () => fetchGpus() }));
const fetchChannels = vi.fn();
vi.mock('$lib/api/channels', () => ({ fetchChannels: () => fetchChannels() }));

const ws = vi.hoisted(() => ({
	handler: null as ((env: unknown) => void) | null,
	unsubscribe: undefined as (() => void) | undefined,
	start: undefined as (() => void) | undefined,
	subscribe: undefined as ((topic: string, h: (env: unknown) => void) => () => void) | undefined
}));
vi.mock('$lib/api/ws', () => ({
	wsClient: {
		start: () => ws.start?.(),
		subscribe: (topic: string, h: (env: unknown) => void) => ws.subscribe?.(topic, h)
	}
}));

const transcoderOn = await vi.hoisted(async () => {
	const { writable } = await import('svelte/store');
	return writable(true);
});
vi.mock('$lib/stores/config', () => ({ transcoderEnabled: { subscribe: transcoderOn.subscribe } }));

import FinishStep from '../FinishStep.svelte';

const view = (over: Partial<SetupView> = {}): SetupView => ({
	completed_at: null,
	progress: {},
	current_step: 'finish',
	admin_default_password: false,
	checklist_dismissed: false,
	...over
});
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
const config = (over: Partial<ConfigView> = {}): ConfigView =>
	({
		makemkv_key: '',
		makemkv_key_valid: false,
		tmdb_api_key: '',
		omdb_api_key: '',
		tvdb_api_key: '',
		search_provider_movie: 'tmdb',
		auto_rip_on_insert: true,
		hold_for_review: false,
		...over
	}) as unknown as ConfigView;
const gpu = (over: Partial<GpuView> = {}): GpuView => ({ id: 'gpu_a', enabled: true, ...over }) as GpuView;
const channel = (type: string): NotificationChannelView => ({ id: type, type, name: type }) as NotificationChannelView;
type Step = { commit(): Promise<string | false> };

function load(
	opts: {
		drives?: DriveView[];
		config?: ConfigView | Error;
		gpus?: GpuView[] | Error;
		channels?: NotificationChannelView[] | Error;
	} = {}
) {
	fetchDrives.mockResolvedValue(opts.drives ?? []);
	const settle = (v: unknown, fallback: unknown) =>
		v instanceof Error ? Promise.reject(v) : Promise.resolve(v ?? fallback);
	fetchConfigView.mockReturnValue(settle(opts.config, config()));
	fetchGpus.mockReturnValue(settle(opts.gpus, []));
	fetchChannels.mockReturnValue(settle(opts.channels, []));
}

function render(over: Partial<SetupView> = {}) {
	return renderComponent(FinishStep, { props: { view: view(over) } });
}

const row = (id: string) => within(screen.getByTestId(`finish-row-${id}`));
const emit = (env: Partial<WSEnvelope>) => ws.handler?.({ event_type: 'rip.started', payload: {}, ...env });

beforeEach(() => {
	ws.handler = null;
	ws.unsubscribe = vi.fn();
	ws.start = vi.fn();
	ws.subscribe = vi.fn((_topic, h) => {
		ws.handler = h;
		return ws.unsubscribe as () => void;
	});
});

afterEach(() => {
	cleanup();
	vi.clearAllMocks();
	transcoderOn.set(true);
});

describe('FinishStep first-disc card', () => {
	it('links to the drives step when no drive is enrolled', async () => {
		load({ drives: [drive({ lifecycle: 'detected' })] });
		render();
		expect(await screen.findByRole('link', { name: 'Enroll a drive to try it.' })).toHaveAttribute(
			'href',
			'/setup/drives'
		);
	});

	it('ignores virtual and offline drives when choosing the target', async () => {
		load({ drives: [drive({ kind: 'virtual' }), drive({ id: 'drv_b', status: 'offline' })] });
		render();
		await waitFor(() => expect(fetchDrives).toHaveBeenCalled());
		expect(await screen.findByRole('link', { name: 'Enroll a drive to try it.' })).toBeInTheDocument();
	});

	it('waits for a disc in the target drive', async () => {
		load({ drives: [drive()] });
		render();
		expect(await screen.findByText(/Waiting for a disc in Front drive\.\.\./)).toBeInTheDocument();
	});

	it('reports a disc detected when the target drive has one loaded', async () => {
		load({ drives: [drive({ media_status: 'loaded' })] });
		render();
		expect(await screen.findByText(/Disc detected in Front drive/)).toBeInTheDocument();
	});

	it('subscribes to the ripper events topic and starts the socket', async () => {
		load();
		render();
		await waitFor(() => expect(ws.subscribe).toHaveBeenCalledWith('ripper.events', expect.any(Function)));
		expect(ws.start).toHaveBeenCalled();
	});

	it('shows ripping started when rip.started arrives for the target drive', async () => {
		load({ drives: [drive({ media_status: 'loaded' })] });
		render();
		await screen.findByText(/Disc detected in Front drive/);
		emit({ payload: { drive_id: 'drv_a' } });
		expect(await screen.findByText(/Ripping started in Front drive/)).toBeInTheDocument();
	});

	it('ignores rip.started for another drive and other event types', async () => {
		load({ drives: [drive()] });
		render();
		await screen.findByText(/Waiting for a disc in Front drive/);
		emit({ payload: { drive_id: 'drv_other' } });
		emit({ event_type: 'rip.finished', payload: { drive_id: 'drv_a' } });
		expect(screen.getByText(/Waiting for a disc in Front drive/)).toBeInTheDocument();
		expect(screen.queryByText(/Ripping started/)).toBeNull();
	});

	it('ignores rip.started while no drive is the target', async () => {
		load();
		render();
		await screen.findByRole('link', { name: 'Enroll a drive to try it.' });
		emit({ payload: { drive_id: 'drv_a' } });
		expect(screen.getByRole('link', { name: 'Enroll a drive to try it.' })).toBeInTheDocument();
	});

	it('unsubscribes when the step is destroyed', async () => {
		load();
		const { unmount } = render();
		await waitFor(() => expect(ws.subscribe).toHaveBeenCalled());
		unmount();
		expect(ws.unsubscribe).toHaveBeenCalled();
	});

	it('tolerates a subscribe that returns nothing when destroyed', async () => {
		load();
		ws.subscribe = vi.fn(() => undefined as unknown as () => void);
		const { unmount } = render();
		await waitFor(() => expect(ws.subscribe).toHaveBeenCalled());
		expect(() => unmount()).not.toThrow();
	});
});

describe('FinishStep summary lines', () => {
	it('counts enrolled (not virtual) and ignored drives', async () => {
		load({
			drives: [
				drive(),
				drive({ id: 'drv_v', kind: 'virtual' }),
				drive({ id: 'drv_i', lifecycle: 'ignored' }),
				drive({ id: 'drv_j', lifecycle: 'ignored' })
			]
		});
		render();
		expect(await row('drives').findByText('1 enrolled, 2 ignored')).toBeInTheDocument();
	});

	it('says the system needs a fix when its step needs attention, and passes otherwise', async () => {
		load();
		const { unmount } = render({ progress: { system: { state: 'attention' } } as SetupView['progress'] });
		expect(await row('system').findByText('Needs a fix on the server, see System check.')).toBeInTheDocument();
		unmount();
		render();
		expect(await row('system').findByText('All checks pass.')).toBeInTheDocument();
	});

	it('always reports the account step as password changed', async () => {
		load();
		render();
		expect(await row('account').findByText('Password changed.')).toBeInTheDocument();
	});

	it('shows Inbox only when the only channel is in-app', async () => {
		load({ channels: [channel('inapp')] });
		render();
		await waitFor(() => expect(fetchChannels).toHaveBeenCalled());
		expect(await row('notifications').findByText('Inbox only')).toBeInTheDocument();
	});

	it('counts one non-in-app channel in the singular', async () => {
		load({ channels: [channel('inapp'), channel('discord')] });
		render();
		expect(await row('notifications').findByText('1 channel')).toBeInTheDocument();
	});

	it('counts two channels in the plural', async () => {
		load({ channels: [channel('discord'), channel('email')] });
		render();
		expect(await row('notifications').findByText('2 channels')).toBeInTheDocument();
	});

	it.each([
		['purchased and valid', { makemkv_key: 'T-abc', makemkv_key_valid: true }, 'Purchased key, valid'],
		['purchased and not valid', { makemkv_key: 'T-abc', makemkv_key_valid: false }, 'Purchased key'],
		['free beta and valid', { makemkv_key: '', makemkv_key_valid: true }, 'Free beta key, valid'],
		['free beta and not valid', { makemkv_key: '', makemkv_key_valid: false }, 'Free beta key']
	])('describes a %s makemkv key', async (_name, over, text) => {
		load({ config: config(over as Partial<ConfigView>) });
		render();
		expect(await row('makemkv').findByText(text)).toBeInTheDocument();
	});

	it('says No lookup key yet when no metadata key is saved', async () => {
		load({ config: config() });
		render();
		expect(await row('metadata').findByText('No lookup key yet')).toBeInTheDocument();
	});

	it('counts one key in the singular and names the movie provider', async () => {
		load({ config: config({ tmdb_api_key: 'k' }) });
		render();
		expect(await row('metadata').findByText('1 key saved. Titles looked up with TMDb.')).toBeInTheDocument();
	});

	it('counts two keys in the plural', async () => {
		load({ config: config({ tmdb_api_key: 'k', omdb_api_key: 'k', search_provider_movie: 'omdb' }) });
		render();
		expect(await row('metadata').findByText('2 keys saved. Titles looked up with OMDb.')).toBeInTheDocument();
	});

	it('names no movie provider on a TVDb-only install', async () => {
		load({ config: config({ tvdb_api_key: 'k' }) });
		render();
		expect(await row('metadata').findByText('1 key saved.')).toBeInTheDocument();
	});

	it.each([
		['manual', { auto_rip_on_insert: false }, 'Manual'],
		['review first', { auto_rip_on_insert: true, hold_for_review: true }, 'Review first'],
		['fully automatic', { auto_rip_on_insert: true, hold_for_review: false }, 'Fully automatic']
	])('describes %s disc handling', async (_name, over, text) => {
		load({ config: config(over as Partial<ConfigView>) });
		render();
		expect(await row('discs').findByText(text)).toBeInTheDocument();
	});

	it('says Ripper only when the transcoder is off', async () => {
		transcoderOn.set(false);
		load({ gpus: [gpu()] });
		render();
		expect(await row('transcoding').findByText('Ripper only')).toBeInTheDocument();
	});

	it('says CPU encoding when no graphics device is enabled', async () => {
		load({ gpus: [gpu({ enabled: false })] });
		render();
		await waitFor(() => expect(fetchGpus).toHaveBeenCalled());
		expect(await row('transcoding').findByText('CPU encoding')).toBeInTheDocument();
	});

	it('counts one enabled graphics device in the singular', async () => {
		load({ gpus: [gpu(), gpu({ id: 'gpu_b', enabled: false })] });
		render();
		expect(await row('transcoding').findByText('1 graphics device enabled')).toBeInTheDocument();
	});

	it('counts two enabled graphics devices in the plural', async () => {
		load({ gpus: [gpu(), gpu({ id: 'gpu_b' })] });
		render();
		expect(await row('transcoding').findByText('2 graphics devices enabled')).toBeInTheDocument();
	});

	it('keeps the fallbacks and drops the config lines when the config fails to load', async () => {
		load({ config: new Error('500'), gpus: [gpu()], channels: [channel('discord')] });
		render();
		expect(await row('transcoding').findByText('1 graphics device enabled')).toBeInTheDocument();
		expect(row('notifications').getByText('1 channel')).toBeInTheDocument();
		for (const id of ['makemkv', 'metadata', 'discs']) {
			expect(within(screen.getByTestId(`finish-row-${id}`)).queryByText(/key|Manual|Review|automatic/i)).toBeNull();
		}
	});

	it('falls back to CPU encoding when the graphics devices fail to load', async () => {
		load({ gpus: new Error('500') });
		render();
		await waitFor(() => expect(fetchGpus).toHaveBeenCalled());
		expect(await row('discs').findByText('Fully automatic')).toBeInTheDocument();
		expect(row('transcoding').getByText('CPU encoding')).toBeInTheDocument();
	});

	it('falls back to Inbox only when the channels fail to load', async () => {
		load({ channels: new Error('500') });
		render();
		expect(await row('discs').findByText('Fully automatic')).toBeInTheDocument();
		expect(row('notifications').getByText('Inbox only')).toBeInTheDocument();
	});
});

describe('FinishStep commit', () => {
	it('resolves done', async () => {
		load();
		const { component } = render();
		expect(await (component as unknown as Step).commit()).toBe('done');
	});
});
