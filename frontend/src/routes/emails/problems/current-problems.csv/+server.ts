import { env } from '$env/dynamic/private';
import type { RequestHandler } from './$types';

const API = env.BACKEND_API_URL || 'http://localhost:8000';

// The browser cannot call Django directly (the session cookie is forwarded
// server-side only), so this streams the CSV through with its download headers.
export const GET: RequestHandler = async ({ cookies, url }) => {
	const headers: Record<string, string> = {};
	const sessionId = cookies.get('sessionid');
	if (sessionId) headers['Cookie'] = `sessionid=${sessionId}`;

	// `action` (remove, review, retry, fix) selects a kind of advice; anything else, "all" included, exports every row.
	const action = url.searchParams.get('action') ?? '';
	const query = ['remove', 'review', 'retry', 'fix'].includes(action)
		? `action=${action}`
		: 'severity=all';
	const response = await fetch(`${API}/api/emails/current-problems.csv?${query}`, { headers });
	if (!response.ok) return new Response('Export failed', { status: response.status });

	return new Response(response.body, {
		headers: {
			'Content-Type': 'text/csv; charset=utf-8',
			'Content-Disposition':
				response.headers.get('Content-Disposition') ??
				'attachment; filename="adresses-a-probleme.csv"'
		}
	});
};
