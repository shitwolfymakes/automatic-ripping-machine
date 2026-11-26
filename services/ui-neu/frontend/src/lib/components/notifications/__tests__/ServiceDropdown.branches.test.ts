import { describe, it, expect, vi, afterEach } from 'vitest';
import { renderComponent, screen, fireEvent, cleanup, within } from '$lib/testing/render';
import ServiceDropdown from '../ServiceDropdown.svelte';
import type { Catalog, CatalogService } from '$lib/types/notifications';

// Branch pins for ServiceDropdown, beside ServiceDropdown.test.ts. Every
// branch is reachable, so none is left open.

function svc(id: string, name: string): CatalogService {
	return { id, name, docs_url: '', url_scheme: id, required_fields: [], advanced_fields: [] };
}

const catalog: Catalog = {
	featured: ['discord', 'missing', 'slack'],
	services: [
		svc('slack', 'Slack'),
		svc('zulip', 'Zulip'),
		svc('discord', 'Discord'),
		svc('gotify', 'Gotify'),
		svc('apprise', 'Apprise')
	]
};

async function openPanel() {
	await fireEvent.click(screen.getAllByRole('button', { expanded: false })[0]);
}

function optionNames(): string[] {
	const list = screen.getByRole('list');
	return within(list)
		.queryAllByRole('button')
		.map((b) => b.querySelector('.service-dropdown-name')?.textContent ?? '');
}

describe('ServiceDropdown groups', () => {
	afterEach(() => cleanup());

	it('lists featured services in catalog order, skipping an unlisted id, then the rest by name', async () => {
		renderComponent(ServiceDropdown, { props: { catalog, selectedId: null } });
		await openPanel();
		expect(optionNames()).toEqual(['Discord', 'Slack', 'Apprise', 'Gotify', 'Zulip']);
		expect(screen.getByText('Featured')).toBeInTheDocument();
		expect(screen.getByText('All services')).toBeInTheDocument();
	});
});

describe('ServiceDropdown search', () => {
	afterEach(() => cleanup());

	async function search(value: string) {
		renderComponent(ServiceDropdown, { props: { catalog, selectedId: null } });
		await openPanel();
		await fireEvent.input(screen.getByPlaceholderText(/search/i), { target: { value } });
	}

	it('matches names case-insensitively and ignores surrounding spaces', async () => {
		await search('  GOTI ');
		expect(optionNames()).toEqual(['Gotify']);
		expect(screen.queryByText('Featured')).toBeNull();
	});

	it('shows the groups for a spaces-only search', async () => {
		await search('   ');
		expect(screen.getByText('Featured')).toBeInTheDocument();
		expect(optionNames()).toHaveLength(5);
	});

	it('shows the empty message when nothing matches', async () => {
		await search('nope');
		expect(screen.getByText('No services match "nope".')).toBeInTheDocument();
		expect(optionNames()).toEqual([]);
	});
});

describe('ServiceDropdown selection', () => {
	afterEach(() => cleanup());

	it('shows the placeholder when selectedId is not in the catalog', () => {
		renderComponent(ServiceDropdown, { props: { catalog, selectedId: 'unknown' } });
		expect(screen.getByText('Select a service...')).toBeInTheDocument();
	});

	it('marks only the selected option as pressed', async () => {
		renderComponent(ServiceDropdown, { props: { catalog, selectedId: 'gotify' } });
		await openPanel();
		const list = screen.getByRole('list');
		expect(within(list).getByRole('button', { name: /Gotify/ })).toHaveAttribute('aria-pressed', 'true');
		expect(within(list).getByRole('button', { name: /Slack/ })).toHaveAttribute('aria-pressed', 'false');
	});
});

describe('ServiceDropdown choosing', () => {
	afterEach(() => cleanup());

	it('calls onpick with the id, closes the panel and clears the search', async () => {
		const onpick = vi.fn();
		renderComponent(ServiceDropdown, { props: { catalog, selectedId: null, onpick } });
		await openPanel();
		await fireEvent.input(screen.getByPlaceholderText(/search/i), { target: { value: 'goti' } });
		await fireEvent.click(screen.getByRole('button', { name: /Gotify/ }));
		expect(onpick).toHaveBeenCalledWith('gotify');
		expect(screen.queryByPlaceholderText(/search/i)).toBeNull();
		await openPanel();
		expect(screen.getByPlaceholderText(/search/i)).toHaveValue('');
	});

	it('closes without error when no onpick prop is given', async () => {
		renderComponent(ServiceDropdown, { props: { catalog, selectedId: null } });
		await openPanel();
		await fireEvent.click(screen.getByRole('button', { name: /Gotify/ }));
		expect(screen.queryByPlaceholderText(/search/i)).toBeNull();
	});
});

describe('ServiceDropdown outside click', () => {
	afterEach(() => cleanup());

	it('closes on a mousedown outside the dropdown', async () => {
		renderComponent(ServiceDropdown, { props: { catalog, selectedId: null } });
		await openPanel();
		await fireEvent.mouseDown(document.body);
		expect(screen.queryByPlaceholderText(/search/i)).toBeNull();
	});

	it('stays open on a mousedown inside the dropdown', async () => {
		renderComponent(ServiceDropdown, { props: { catalog, selectedId: null } });
		await openPanel();
		await fireEvent.mouseDown(screen.getByPlaceholderText(/search/i));
		expect(screen.getByPlaceholderText(/search/i)).toBeInTheDocument();
	});

	it('ignores a mousedown outside once closed', async () => {
		const remove = vi.spyOn(document, 'removeEventListener');
		renderComponent(ServiceDropdown, { props: { catalog, selectedId: null } });
		await openPanel();
		await fireEvent.mouseDown(document.body);
		expect(remove).toHaveBeenCalledWith('mousedown', expect.any(Function), true);
		await fireEvent.mouseDown(document.body);
		expect(screen.queryByPlaceholderText(/search/i)).toBeNull();
		remove.mockRestore();
	});
});
