import { describe, it, expect, afterEach } from 'vitest';
import { renderComponent, screen, cleanup, fireEvent } from '$lib/testing/render';
import EnvironmentSection from '../EnvironmentSection.svelte';
import { tabFromHash } from '$lib/settings/tabs';
import type { EnvGroupView } from '$lib/types/api.gen';

const groups: EnvGroupView[] = [
	{
		name: 'Paths',
		vars: [
			{ key: 'RAW_ROOT', value: '/raw', secret: false, is_set: true, source: 'default' },
			{ key: 'ARM_SERVICE_TOKEN', value: null, secret: true, is_set: true, source: 'env' }
		]
	},
	{
		name: 'Transcoding',
		vars: [
			{
				key: 'MAX_PARALLEL_TRANSCODES',
				value: '2',
				secret: false,
				is_set: true,
				source: 'env',
				effective: { value: '4', setting_key: 'max_parallel_transcodes', tab: 'Transcoding' }
			}
		]
	},
	{ name: 'Logging', vars: [{ key: 'ARM_LOG_LEVEL', value: 'INFO', secret: false, is_set: true, source: 'env' }] }
];

describe('EnvironmentSection', () => {
	afterEach(cleanup);

	it('renders a section per group with masked secrets', () => {
		renderComponent(EnvironmentSection, { props: { groups, logLevels: [] } });
		expect(screen.getByRole('button', { name: /Paths/ })).toBeInTheDocument();
		expect(screen.getByTestId('env-ARM_SERVICE_TOKEN')).toHaveTextContent('set');
		expect(screen.getByTestId('env-ARM_SERVICE_TOKEN')).not.toHaveTextContent('not set');
		expect(screen.getByTestId('env-RAW_ROOT')).toHaveTextContent('default');
	});

	it('shows the in-use value with a link to its settings field', () => {
		renderComponent(EnvironmentSection, { props: { groups, logLevels: [] } });
		const link = screen.getByRole('link', { name: /in use: 4/ });
		expect(link).toHaveAttribute('href', '#transcoding/max_parallel_transcodes');
		expect(link).toHaveTextContent('Settings, Transcoding');
		expect(tabFromHash(link.getAttribute('href') ?? '')).toBe('transcoding');
	});

	it('logging group lists per-service levels', () => {
		renderComponent(EnvironmentSection, {
			props: { groups, logLevels: [{ name: 'arm-ripper', log_level: 'DEBUG' }] }
		});
		expect(screen.getByTestId('diag-level-arm-ripper')).toHaveTextContent('DEBUG');
	});

	it('collapses a group on click', async () => {
		renderComponent(EnvironmentSection, { props: { groups, logLevels: [] } });
		await fireEvent.click(screen.getByRole('button', { name: /Paths/ }));
		expect(screen.queryByTestId('env-RAW_ROOT')).toBeNull();
	});
});
