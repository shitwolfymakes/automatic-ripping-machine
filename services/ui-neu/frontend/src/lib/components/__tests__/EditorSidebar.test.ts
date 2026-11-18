import { it, expect, vi, afterEach } from 'vitest';
import { renderComponent, screen, fireEvent, cleanup, within } from '$lib/test-utils';
import EditorSidebarHarness from './EditorSidebarHarness.svelte';

afterEach(cleanup);

it('renders the title, the header action, the body and a footer region', () => {
	renderComponent(EditorSidebarHarness);
	const dialog = screen.getByRole('dialog', { name: 'Editor title' });
	expect(within(dialog).getByRole('heading', { name: 'Editor title' })).toBeInTheDocument();
	expect(within(dialog).getByRole('button', { name: 'Header action' })).toBeInTheDocument();
	expect(within(dialog).getByTestId('body')).toBeInTheDocument();
	expect(within(screen.getByTestId('editor-sidebar-footer')).getByText('Footer content')).toBeInTheDocument();
	expect(dialog).toContainElement(screen.getByTestId('editor-sidebar-footer'));
});

it('puts the footer after the body, outside the scrolling area', () => {
	renderComponent(EditorSidebarHarness);
	const body = screen.getByTestId('body');
	const footer = screen.getByTestId('editor-sidebar-footer');
	expect(body.compareDocumentPosition(footer) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
	expect(body.parentElement).not.toContainElement(footer);
});

it('Close calls onclose', async () => {
	const onclose = vi.fn();
	renderComponent(EditorSidebarHarness, { props: { onclose } });
	await fireEvent.click(screen.getByRole('button', { name: 'Close' }));
	expect(onclose).toHaveBeenCalledOnce();
});

it('Escape calls onclose', async () => {
	const onclose = vi.fn();
	renderComponent(EditorSidebarHarness, { props: { onclose } });
	await fireEvent.keyDown(document, { key: 'Escape' });
	expect(onclose).toHaveBeenCalledOnce();
});

it('the form width and the wide width are separate panel classes', () => {
	renderComponent(EditorSidebarHarness);
	expect(screen.getByRole('dialog')).toHaveClass('editor-sidebar-form');
	cleanup();
	renderComponent(EditorSidebarHarness, { props: { width: 'wide' } });
	expect(screen.getByRole('dialog')).toHaveClass('editor-sidebar-wide');
});

it('a stacked sidebar layers above another one', () => {
	renderComponent(EditorSidebarHarness, { props: { stacked: true } });
	expect(screen.getByRole('dialog')).toHaveAttribute('data-stacked', 'true');
});

it('works without header actions', () => {
	renderComponent(EditorSidebarHarness, { props: { withActions: false } });
	expect(screen.queryByRole('button', { name: 'Header action' })).not.toBeInTheDocument();
});

it('draws no footer strip when the footer is omitted', () => {
	renderComponent(EditorSidebarHarness, { props: { withFooter: false } });
	expect(screen.getByTestId('body')).toBeInTheDocument();
	expect(screen.queryByTestId('editor-sidebar-footer')).not.toBeInTheDocument();
});
