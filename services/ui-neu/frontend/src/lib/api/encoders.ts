import type { EncoderAvailabilityView } from '$lib/types/api.gen';
import { get } from './client';

// The arm_common.encoders catalog, in catalog order, with availability
// computed server-side from the live gpus inventory (GET /api/encoders).
export function fetchEncoders(): Promise<EncoderAvailabilityView[]> {
	return get<EncoderAvailabilityView[]>('/api/encoders');
}
