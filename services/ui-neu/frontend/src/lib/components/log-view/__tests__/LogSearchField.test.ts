// The log terminal's search box, rendered through a harness that binds its text and matchCase.
import { describe, it, expect, afterEach } from 'vitest';
import { renderComponent, screen, fireEvent, cleanup } from '$lib/test-utils';
import LogSearchFieldHarness from './LogSearchFieldHarness.svelte';

type Defaults = NonNullable<Parameters<typeof renderComponent>[1]>;

function renderField(props: Record<string, unknown> = {}) {
	return renderComponent(LogSearchFieldHarness, { props } as Defaults);
}

const input = () => screen.getByTestId('job-log-search') as HTMLInputElement;

describe('LogSearchField', () => {
	afterEach(cleanup);

	it('shows the bound text in the input', () => {
		renderField({ initialText: 'disc' });
		expect(input().value).toBe('disc');
	});

	it('updates the bound text as the user types', async () => {
		renderField();
		await fireEvent.input(input(), { target: { value: 'abc' } });
		expect(screen.getByTestId('bound-text')).toHaveTextContent('abc');
	});

	it('hides the count and Clear filter while the text is empty', () => {
		renderField({ matches: 3 });
		expect(screen.queryByTestId('job-log-search-count')).toBeNull();
		expect(screen.queryByRole('button', { name: 'Clear filter' })).toBeNull();
	});

	it('shows "1 match" for one line while there is a query', () => {
		renderField({ initialText: 'x', matches: 1 });
		expect(screen.getByTestId('job-log-search-count')).toHaveTextContent('1 match');
		expect(screen.getByRole('button', { name: 'Clear filter' })).toBeInTheDocument();
	});

	it('shows "2 matches" for two lines while there is a query', () => {
		renderField({ initialText: 'x', matches: 2 });
		expect(screen.getByTestId('job-log-search-count')).toHaveTextContent('2 matches');
	});

	it('Clear filter empties the bound text and focuses the input', async () => {
		renderField({ initialText: 'x', matches: 1 });
		await fireEvent.click(screen.getByRole('button', { name: 'Clear filter' }));
		expect(screen.getByTestId('bound-text')).toHaveTextContent('');
		expect(input().value).toBe('');
		expect(input()).toHaveFocus();
	});

	it('Aa flips the bound matchCase and its aria-pressed', async () => {
		renderField();
		const aa = screen.getByTestId('job-log-search-case');
		expect(aa).toHaveAttribute('aria-pressed', 'false');
		await fireEvent.click(aa);
		expect(aa).toHaveAttribute('aria-pressed', 'true');
		expect(screen.getByTestId('bound-match-case')).toHaveTextContent('true');
		await fireEvent.click(aa);
		expect(aa).toHaveAttribute('aria-pressed', 'false');
		expect(screen.getByTestId('bound-match-case')).toHaveTextContent('false');
	});

	it('focus() focuses the input', () => {
		const { component } = renderField();
		expect(input()).not.toHaveFocus();
		(component as unknown as { focusField(): void }).focusField();
		expect(input()).toHaveFocus();
	});
});
