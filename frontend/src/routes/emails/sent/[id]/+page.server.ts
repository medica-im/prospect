import { env } from '$env/dynamic/private';
import { error } from '@sveltejs/kit';
import type { PageServerLoad } from './$types';

const API = env.BACKEND_API_URL || 'http://localhost:8000';

export const load: PageServerLoad = async ({ params, fetch }) => {
	const response = await fetch(`${API}/api/emails/sent/${params.id}/preview`);

	if (!response.ok) {
		error(404, 'Sent email not found');
	}

	const preview = await response.json();
	return { preview };
};
