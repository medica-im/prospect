import { env } from '$env/dynamic/private';
import type { PageServerLoad } from './$types';

const API = env.BACKEND_API_URL || 'http://localhost:8000';

export const load: PageServerLoad = async ({ cookies }) => {
	const headers: Record<string, string> = {};
	const sessionId = cookies.get('sessionid');
	if (sessionId) headers['Cookie'] = `sessionid=${sessionId}`;

	const [response, unsubRes] = await Promise.all([
		fetch(`${API}/api/emails/sent`, { headers }),
		fetch(`${API}/api/unsubscribes`, { headers })
	]);

	const sentEmails = response.ok ? await response.json() : [];
	const unsubscribed: string[] = unsubRes.ok
		? (await unsubRes.json()).map((u: { email: string }) => u.email)
		: [];

	return { sentEmails, unsubscribed };
};
