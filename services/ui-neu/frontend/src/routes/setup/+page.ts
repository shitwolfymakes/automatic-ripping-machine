import { redirect, isRedirect } from '@sveltejs/kit';
import { fetchSetup } from '$lib/api/setup';

// /setup resumes at the first step without a recorded state.
export async function load() {
	let step = 'account';
	try {
		step = (await fetchSetup()).current_step;
	} catch (e) {
		if (isRedirect(e)) throw e;
	}
	redirect(307, `/setup/${step}`);
}
