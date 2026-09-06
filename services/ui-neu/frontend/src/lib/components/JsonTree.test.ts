import { describe, it, expect, afterEach } from 'vitest';
import { renderComponent, screen, cleanup, fireEvent } from '$lib/test-utils';
import JsonTree from './JsonTree.svelte';

describe('JsonTree', () => {
	afterEach(() => cleanup());

	it('renders a scalar as name: value with no disclosure button', () => {
		renderComponent(JsonTree, { props: { name: 'disc_type', value: 'dvd' } });
		expect(screen.getByText('disc_type')).toBeInTheDocument();
		expect(screen.getByText('dvd')).toBeInTheDocument();
		expect(screen.queryByRole('button')).not.toBeInTheDocument();
	});

	it('renders a container as a disclosure button with a preview', () => {
		renderComponent(JsonTree, { props: { name: 'scan_result', value: { a: 1 }, depth: 0 } });
		const btn = screen.getByRole('button');
		expect(btn).toHaveTextContent('scan_result');
		expect(btn).toHaveTextContent('{...}');
	});

	it('is open at depth 0 (children visible)', () => {
		renderComponent(JsonTree, { props: { name: 'root', value: { child_key: 'child_val' }, depth: 0 } });
		expect(screen.getByText('child_key')).toBeInTheDocument();
		expect(screen.getByText('child_val')).toBeInTheDocument();
	});

	it('is collapsed at depth 2 (children hidden until clicked)', async () => {
		renderComponent(JsonTree, { props: { name: 'deep', value: { hidden_key: 'hidden_val' }, depth: 2 } });
		expect(screen.queryByText('hidden_key')).not.toBeInTheDocument();
		await fireEvent.click(screen.getByRole('button'));
		expect(screen.getByText('hidden_key')).toBeInTheDocument();
	});

	it('toggles a node closed when clicked while open', async () => {
		renderComponent(JsonTree, { props: { name: 'root', value: { k: 'v' }, depth: 0 } });
		expect(screen.getByText('k')).toBeInTheDocument();
		await fireEvent.click(screen.getByRole('button'));
		expect(screen.queryByText('k')).not.toBeInTheDocument();
	});

	it('renders an empty object inline (no disclosure button)', () => {
		renderComponent(JsonTree, { props: { name: 'raw', value: {}, depth: 0 } });
		expect(screen.getByText('raw')).toBeInTheDocument();
		expect(screen.getByText('{}')).toBeInTheDocument();
		expect(screen.queryByRole('button')).not.toBeInTheDocument();
	});

	it('recurses: nested array reachable, deep item collapsed', async () => {
		renderComponent(JsonTree, {
			props: { name: 'scan_result', value: { titles: [{ index: 0 }] }, depth: 0 }
		});
		// depth 0 (scan_result) open, depth 1 (titles) open → "titles" disclosure visible
		expect(screen.getByText('titles')).toBeInTheDocument();
		// titles is an array container; its [0] child sits at depth 2 → collapsed,
		// so the leaf "index" is not yet shown.
		expect(screen.queryByText('index')).not.toBeInTheDocument();
	});
});
