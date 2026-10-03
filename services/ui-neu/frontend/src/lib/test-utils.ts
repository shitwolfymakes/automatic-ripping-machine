import { render } from '@testing-library/svelte';

export { screen, fireEvent, within, waitFor, cleanup } from '@testing-library/svelte';

// Any component render() accepts. Props stay loosely typed so tests can pass
// partial props without fighting Svelte 5 component generics.
type RenderableComponent = Parameters<typeof render>[0];

// Thin wrapper, extensible for future context providers or global setup.
export function renderComponent(component: RenderableComponent, options: Record<string, unknown> = {}) {
	return render(component, options);
}
