import { env } from '$env/dynamic/private';
import { redirect } from '@sveltejs/kit';
import type { PageServerLoad } from './$types';

const API = env.BACKEND_API_URL || 'http://localhost:8000';

// Always loads every severity: the page filters client-side, so switching the
// filter does not re-read Twenty. `?refresh=1` re-reads Twenty once, then
// redirects to the clean URL so a later reload is served from the fresh cache.
export const load: PageServerLoad = async ({ cookies, url }) => {
	const headers: Record<string, string> = {};
	const sessionId = cookies.get('sessionid');
	if (sessionId) headers['Cookie'] = `sessionid=${sessionId}`;

	const refresh = url.searchParams.get('refresh') === '1';
	const response = await fetch(
		`${API}/api/emails/current-problems?severity=all${refresh ? '&refresh=true' : ''}`,
		{ headers }
	);
	if (refresh) redirect(303, url.pathname);

	if (!response.ok) return { problems: null, status: response.status };
	return { problems: await response.json(), status: 200 };
};
