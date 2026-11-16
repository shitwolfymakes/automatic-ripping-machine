import { describe, it, expect, afterEach } from 'vitest';
import { renderComponent, screen, cleanup } from '$lib/testing/render';
import ConfigSchemaField from '../ConfigSchemaField.svelte';
import type { ConfigFieldMeta } from '$lib/types/api.gen';

// The docs "i" beside each schema-driven setting: config.<key> from the registry.
const f = (over: Partial<ConfigFieldMeta>): ConfigFieldMeta => ({
	key: 'k',
	group: 'G',
	tier: 'operator',
	label: 'Label',
	help: 'Help',
	type: 'string',
	editable: true,
	enum_values: null,
	...over
});

const docs = (label: string) => screen.getByRole('link', { name: `Docs for ${label} (opens in a new tab)` });

afterEach(() => cleanup());

describe('ConfigSchemaField docs link', () => {
	it('links a mapped text field to its registry page, beside a label that names the input', () => {
		renderComponent(ConfigSchemaField, {
			props: {
				field: f({
					key: 'tmdb_api_key',
					label: 'TMDb API key',
					signup_url: 'https://www.themoviedb.org/signup'
				}),
				value: ''
			}
		});
		expect(docs('TMDb API key')).toHaveAttribute('href', 'https://developer.themoviedb.org/docs/getting-started');
		expect(docs('TMDb API key')).toHaveAttribute('data-field-id', 'config.tmdb_api_key');
		const input = screen.getByRole('textbox', { name: 'TMDb API key' });
		expect(document.querySelector('label.field-label')).toHaveAttribute('for', input.id);
		expect(screen.getByRole('link', { name: /Get a free key/ })).toHaveAttribute(
			'href',
			'https://www.themoviedb.org/signup'
		);
		expect(screen.getByText('Help')).toBeInTheDocument();
	});

	it('shows no link for an opted-out field', () => {
		renderComponent(ConfigSchemaField, {
			props: { field: f({ key: 'BIND_PORT', type: 'int', label: 'Port' }), value: 8080 }
		});
		expect(screen.getByRole('spinbutton', { name: 'Port' })).toHaveAttribute('id', 'setting-control-BIND_PORT');
		expect(screen.queryByRole('link')).toBeNull();
	});

	it('labels a checkbox through for and links its docs outside the label', () => {
		renderComponent(ConfigSchemaField, {
			props: { field: f({ key: 'auto_rip_on_insert', type: 'bool', label: 'Auto-rip' }), value: false }
		});
		const box = screen.getByRole('checkbox', { name: 'Auto-rip' });
		const label = screen.getByText('Auto-rip');
		expect(label).toHaveAttribute('for', box.id);
		expect(label).not.toContainElement(docs('Auto-rip'));
		expect(docs('Auto-rip')).toHaveAttribute('href', '/help/guide/configuring-arm#rip--transcode-behaviour');
	});

	it('names a select and a secret through for', () => {
		renderComponent(ConfigSchemaField, {
			props: {
				field: f({ key: 'search_provider_movie', type: 'enum', label: 'Provider', enum_values: ['tmdb'] }),
				value: 'tmdb'
			}
		});
		expect(screen.getByRole('combobox', { name: 'Provider' })).toHaveAttribute(
			'id',
			'setting-control-search_provider_movie'
		);
		expect(docs('Provider')).toBeInTheDocument();
		cleanup();
		renderComponent(ConfigSchemaField, {
			props: { field: f({ key: 'omdb_api_key', tier: 'secret', label: 'OMDb key' }), value: '' }
		});
		expect(document.getElementById('setting-control-omdb_api_key')).toBe(screen.getByLabelText('OMDb key'));
		expect(docs('OMDb key')).toHaveAttribute('href', 'https://www.omdbapi.com/');
	});

	it('captions a ranked list and a read-only value, each with its link', () => {
		renderComponent(ConfigSchemaField, {
			props: {
				field: f({ key: 'movie_sources', type: 'ranked', label: 'Movie sources', enum_values: ['tmdb'] }),
				value: ['tmdb']
			}
		});
		expect(docs('Movie sources')).toBeInTheDocument();
		cleanup();
		renderComponent(ConfigSchemaField, {
			props: { field: f({ key: 'ARM_GPUS', editable: false, label: 'GPUs' }), value: 'all' }
		});
		expect(screen.getByText('GPUs').tagName).toBe('SPAN');
		expect(docs('GPUs').getAttribute('href')).toMatch(/^\/help\/guide\/hardware-transcoding/);
	});
});
