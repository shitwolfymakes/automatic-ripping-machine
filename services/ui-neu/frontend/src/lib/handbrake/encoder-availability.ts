import type { EncoderAvailabilityView } from '$lib/types/api.gen';

/** The availability entry whose catalog id is `id`, if the catalog lists it. */
export function findAvailability(
	availability: EncoderAvailabilityView[],
	id: string
): EncoderAvailabilityView | undefined {
	return availability.find((a) => a.id === id);
}

/** The catalog label of encoder `id`, or `fallback` when the catalog does not list it. */
export function availabilityLabel(availability: EncoderAvailabilityView[], id: string, fallback: string): string {
	return findAvailability(availability, id)?.label ?? fallback;
}
