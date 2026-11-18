// The phase LoadState renders: the error, the anti-flicker wait, the
// loading skeleton, the empty state, or the data.

/** What LoadState renders. */
type LoadPhase = 'error' | 'waiting' | 'loading' | 'empty' | 'ready';

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
 * The phase for the inputs. With no `isEmpty`, only an empty array is
 * empty.
 */
export function loadPhase<T>(s: LoadInputs<T>): LoadPhase {
	if (s.error) return 'error';
	if (s.loading && s.delayElapsed) return 'loading';
	if (s.loading) return 'waiting';
	if (s.data == null) return 'loading';
	const emptyCheck = s.isEmpty ?? defaultIsEmpty;
	if (emptyCheck(s.data)) return 'empty';
	return 'ready';
}
