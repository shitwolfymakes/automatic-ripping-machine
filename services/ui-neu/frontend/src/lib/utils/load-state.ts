// The phase LoadState renders: the error, the anti-flicker wait, the
// loading skeleton, the empty state, or the data.

/** What LoadState renders: the error and the data travel with the phases that show them. */
export type LoadView<T> =
	| { phase: 'error'; error: Error }
	| { phase: 'waiting' }
	| { phase: 'loading' }
	| { phase: 'empty' }
	| { phase: 'ready'; data: T };

/** The inputs that pick the phase. */
export interface LoadInputs<T> {
	data: T | null | undefined;
	loading: boolean;
	error: Error | null;
	/** The loading has lasted longer than the component's minimum delay. */
	delayElapsed: boolean;
	isEmpty?: (data: T) => boolean;
}

function defaultIsEmpty(d: unknown): boolean {
	if (Array.isArray(d)) return d.length === 0;
	return false;
}

/**
 * The view for the inputs. With no `isEmpty`, only an empty array is
 * empty.
 */
export function loadView<T>(s: LoadInputs<T>): LoadView<T> {
	if (s.error) return { phase: 'error', error: s.error };
	if (s.loading && s.delayElapsed) return { phase: 'loading' };
	if (s.loading) return { phase: 'waiting' };
	if (s.data == null) return { phase: 'loading' };
	const emptyCheck = s.isEmpty ?? defaultIsEmpty;
	if (emptyCheck(s.data)) return { phase: 'empty' };
	return { phase: 'ready', data: s.data };
}
