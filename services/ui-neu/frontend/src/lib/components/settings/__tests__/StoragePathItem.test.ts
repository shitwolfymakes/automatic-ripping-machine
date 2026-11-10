import { describe, it, expect, afterEach } from 'vitest';
import { renderComponent, screen, cleanup, within } from '$lib/test-utils';
import type { PathStatus, StorageRoot } from '$lib/types/api.gen';
import StoragePathItem from '../StoragePathItem.svelte';

const folder = (over: Partial<PathStatus> = {}): PathStatus => ({
	name: 'MEDIA_ROOT',
	path: '/media',
	exists: true,
	writable: true,
	...over
});
const root = (over: Partial<StorageRoot> = {}): StorageRoot => ({
	name: 'MEDIA_ROOT',
	path: '/media',
	total_gb: 1000,
	used_gb: 249,
	free_gb: 750.6,
	percent: 25,
	...over
});

describe('StoragePathItem', () => {
	afterEach(() => cleanup());

	it('shows a writable folder as ok with no fix footer', () => {
		renderComponent(StoragePathItem, { props: { folder: folder(), storage: null } });
		const card = screen.getByTestId('system-health-path');
		expect(card).toHaveAttribute('data-status', 'ok');
		expect(within(card).getByText('OK')).toBeInTheDocument();
		expect(within(card).getByText('Exists')).toBeInTheDocument();
		expect(within(card).getByText('Writable')).toBeInTheDocument();
		expect(within(card).queryByText(/Run this on the server/)).toBeNull();
		expect(within(card).queryByText(/Set ARM_HOST_/)).toBeNull();
	});

	it('offers the chown command for a read-only folder with a host path', () => {
		renderComponent(StoragePathItem, {
			props: {
				folder: folder({ writable: false, host_path: '/srv/media', uid: 1000, gid: 1001 }),
				storage: null
			}
		});
		const card = screen.getByTestId('system-health-path');
		expect(card).toHaveAttribute('data-status', 'warning');
		expect(within(card).getByText('Problem')).toBeInTheDocument();
		expect(within(card).getByText('Not writable')).toBeInTheDocument();
		expect(within(card).getByText('/srv/media')).toBeInTheDocument();
		expect(within(card).getByText('sudo chown -R 1000:1001 /srv/media')).toBeInTheDocument();
	});

	it('shows the .env hint for a missing folder without a host path', () => {
		renderComponent(StoragePathItem, {
			props: { folder: folder({ exists: false, writable: false }), storage: null }
		});
		const card = screen.getByTestId('system-health-path');
		expect(card).toHaveAttribute('data-status', 'error');
		expect(within(card).getByText('Missing')).toBeInTheDocument();
		expect(
			within(card).getByText('Set ARM_HOST_*_PATH in .env so ARM can name the folder to fix.')
		).toBeInTheDocument();
	});

	it('shows the rounded free space from the matching storage root', () => {
		renderComponent(StoragePathItem, { props: { folder: folder(), storage: [root()] } });
		expect(screen.getByText('751 GB free')).toBeInTheDocument();
	});

	it('shows Measuring... with no storage', () => {
		renderComponent(StoragePathItem, { props: { folder: folder(), storage: null } });
		expect(screen.getByText('Measuring...')).toBeInTheDocument();
	});

	it('shows Measuring... when no storage root has the folder name', () => {
		renderComponent(StoragePathItem, {
			props: { folder: folder(), storage: [root({ name: 'RAW_ROOT' })] }
		});
		expect(screen.getByText('Measuring...')).toBeInTheDocument();
	});

	it('shows a known root by its label with its help line', () => {
		renderComponent(StoragePathItem, { props: { folder: folder(), storage: null } });
		expect(screen.getByText('Media library')).toBeInTheDocument();
		expect(screen.getByText('Finished files are filed here.')).toBeInTheDocument();
	});

	it('shows an unknown root by its name with an empty help line', () => {
		renderComponent(StoragePathItem, {
			props: { folder: folder({ name: 'CUSTOM_ROOT', path: '/custom' }), storage: null }
		});
		const card = screen.getByTestId('system-health-path');
		expect(within(card).getByText('CUSTOM_ROOT')).toBeInTheDocument();
		expect(within(card).queryByText('Finished files are filed here.')).toBeNull();
	});
});
