import { env } from '$env/dynamic/private';
import type { RequestHandler } from './$types';

const API = env.BACKEND_API_URL || 'http://localhost:8000';

export const POST: RequestHandler = async ({ request, cookies }) => {
	const sessionId = cookies.get('sessionid');
	const headers: Record<string, string> = {};
	if (sessionId) headers['Cookie'] = `sessionid=${sessionId}`;

	const formData = await request.formData();

	const response = await fetch(`${API}/api/twenty/upload-csv`, {
		method: 'POST',
		headers,
		body: formData
	});

	const json = await response.json();
	return new Response(JSON.stringify(json), {
		status: response.status,
		headers: { 'Content-Type': 'application/json' }
	});
};
