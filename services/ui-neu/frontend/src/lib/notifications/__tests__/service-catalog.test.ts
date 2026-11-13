import { describe, it, expect } from 'vitest';
import { serviceGroups, matchingServices } from '../service-catalog';
import type { Catalog, CatalogService } from '$lib/types/notifications';

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

describe('serviceGroups', () => {
	it('lists featured services in the featured order, not the services order', () => {
		expect(serviceGroups(catalog).featured.map((s) => s.id)).toEqual(['discord', 'slack']);
	});

	it('skips a featured id the services do not list', () => {
		expect(serviceGroups(catalog).featured.map((s) => s.id)).not.toContain('missing');
	});

	it('lists every other service sorted by name', () => {
		expect(serviceGroups(catalog).rest.map((s) => s.name)).toEqual(['Apprise', 'Gotify', 'Zulip']);
	});

	it('gives two empty groups for an empty catalog', () => {
		expect(serviceGroups({ featured: [], services: [] })).toEqual({ featured: [], rest: [] });
	});
});

describe('matchingServices', () => {
	it('gives null for an empty search', () => {
		expect(matchingServices(catalog, '')).toBeNull();
	});

	it('gives null for a spaces-only search', () => {
		expect(matchingServices(catalog, '   ')).toBeNull();
	});

	it('matches ignoring case and surrounding spaces', () => {
		expect(matchingServices(catalog, '  GO ')?.map((s) => s.id)).toEqual(['gotify']);
	});

	it('gives an empty list when nothing matches', () => {
		expect(matchingServices(catalog, 'nope')).toEqual([]);
	});
});
