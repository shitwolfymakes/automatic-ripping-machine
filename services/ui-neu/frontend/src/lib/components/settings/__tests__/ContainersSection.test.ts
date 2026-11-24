import { describe, it, expect, afterEach } from 'vitest';
import { renderComponent, screen, cleanup } from '$lib/test-utils';
import ContainersSection from '../ContainersSection.svelte';
import type { ContainerView } from '$lib/types/api.gen';

// Branches not forced here: the `?? ''` fallbacks Svelte compiles around the
// text and attribute expressions `{m.host}`, `{m.container}`, `{m.mode}`,
// `{e.key}`, the whole `{e.secret ? '<secret>' : (e.value ?? '')}` and the
// `{c.label}` in `data-testid`. Each is a required string on ContainerView /
// ContainerMountView / ContainerEnvView (the ternary always yields a string),
// so none is ever nullish.

const containers: ContainerView[] = [
	{
		kind: 'ripper',
		label: 'arm-ripper',
		state: 'running',
		image: 'arm:latest',
		network: 'arm',
		docker_host: null,
		mounts: [{ host: '/h', container: '/c', mode: 'rw' }],
		devices: ['/dev/sr0'],
		env: [
			{ key: 'A', value: 'x', secret: false },
			{ key: 'TOKEN', value: null, secret: true }
		]
	}
];

describe('ContainersSection', () => {
	afterEach(cleanup);

	it('renders a collapsed details per container with its facts', () => {
		renderComponent(ContainersSection, { props: { containers } });
		const d = screen.getByTestId('container-0-arm-ripper') as HTMLDetailsElement;
		expect(d.open).toBe(false);
		expect(d).toHaveTextContent('arm:latest');
		expect(d).toHaveTextContent('/h : /c (rw)');
		expect(d).toHaveTextContent('/dev/sr0');
		expect(d).toHaveTextContent('A=x');
		expect(d).toHaveTextContent('TOKEN=<secret>');
	});

	it('renders two containers with identical kind and label', () => {
		const twin = { ...containers[0], label: 'Same Drive' };
		renderComponent(ContainersSection, { props: { containers: [twin, { ...twin }] } });
		expect(screen.getByTestId('container-0-Same Drive')).toBeInTheDocument();
		expect(screen.getByTestId('container-1-Same Drive')).toBeInTheDocument();
	});

	it('renders nothing without containers', () => {
		renderComponent(ContainersSection, { props: { containers: [] } });
		expect(screen.queryByTestId('containers-section')).toBeNull();
	});

	it('shows an unknown state and a blank public env value', () => {
		const c = { ...containers[0], state: null, env: [{ key: 'EMPTY', value: null, secret: false }] };
		renderComponent(ContainersSection, { props: { containers: [c] } });
		const d = screen.getByTestId('container-0-arm-ripper');
		expect(d).toHaveTextContent('unknown');
		expect(d).toHaveTextContent(/EMPTY=$/);
	});
});
