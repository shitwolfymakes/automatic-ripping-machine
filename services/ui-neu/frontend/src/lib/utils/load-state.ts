// The phase LoadState renders: the error, the anti-flicker wait, the
// loading skeleton, the empty state, or the data.

/** What LoadState renders. */
type LoadPhase = 'error' | 'waiting' | 'loading' | 'empty' | 'ready';

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
 * The phase for the inputs. A skeleton on screen stays until the gate
 * releases it, even once the data is in. With no `isEmpty`, only an empty
 * array is empty.
 */
export function loadPhase<T>(s: LoadInputs<T>): LoadPhase {
	if (s.error) return 'error';
	if (s.skeletonShown) return 'loading';
	if (isPending(s)) return 'waiting';
	const emptyCheck = s.isEmpty ?? defaultIsEmpty;
	if (emptyCheck(s.data as T)) return 'empty';
	return 'ready';
}
