import { env } from '$env/dynamic/private';
import type { RequestHandler } from './$types';

const API = env.BACKEND_API_URL || 'http://localhost:8000';

export const POST: RequestHandler = async ({ request, cookies }) => {
	const sessionId = cookies.get('sessionid');
	const headers: Record<string, string> = { 'Content-Type': 'application/json' };
	if (sessionId) headers['Cookie'] = `sessionid=${sessionId}`;

	const body = await request.json();

	const response = await fetch(
		`${API}/api/twenty/preview?upload_id=${body.upload_id}&transformer_id=${body.transformer_id}`,
		{ method: 'POST', headers }
	);

	const json = await response.json();
	return new Response(JSON.stringify(json), {
		status: response.status,
		headers: { 'Content-Type': 'application/json' }
	});
};
