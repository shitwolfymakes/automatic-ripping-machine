import { error } from '@sveltejs/kit';
import type { SetupStep } from '$lib/types/api.gen';
import { stepMeta } from '$lib/components/setup/steps';

export function load({ params }: { params: { step: string } }) {
	if (!stepMeta(params.step)) error(404, 'Unknown setup step');
	return { step: params.step as SetupStep };
}
