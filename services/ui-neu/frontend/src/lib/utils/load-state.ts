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
	/** The skeleton gate has the skeleton on screen (see SkeletonGate). */
	skeletonShown: boolean;
	isEmpty?: (data: T) => boolean;
}

function defaultIsEmpty(d: unknown): boolean {
	if (Array.isArray(d)) return d.length === 0;
	return false;
}

/** Nothing to show yet: a load is running, or none has produced data. */
export function isPending<T>(s: Pick<LoadInputs<T>, 'data' | 'loading' | 'error'>): boolean {
	return !s.error && (s.loading || s.data == null);
}

/**
 * The view for the inputs: the phase, with the error or the data for the
 * phases that show them. A skeleton on screen stays until the gate releases
 * it, even once the data is in. With no `isEmpty`, only an empty array is
 * empty.
 */
export function loadView<T>(s: LoadInputs<T>): LoadView<T> {
	if (s.error) return { phase: 'error', error: s.error };
	if (s.skeletonShown) return { phase: 'loading' };
	if (isPending(s)) return { phase: 'waiting' };
	const data = s.data as T;
	const emptyCheck = s.isEmpty ?? defaultIsEmpty;
	if (emptyCheck(data)) return { phase: 'empty' };
	return { phase: 'ready', data };
}
