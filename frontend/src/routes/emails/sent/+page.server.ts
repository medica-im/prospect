import { env } from '$env/dynamic/private';
import type { PageServerLoad } from './$types';

const API = env.BACKEND_API_URL || 'http://localhost:8000';

export const load: PageServerLoad = async ({ fetch }) => {
	const response = await fetch(`${API}/api/emails/sent`);
	const sentEmails = response.ok ? await response.json() : [];
	return { sentEmails };
};
