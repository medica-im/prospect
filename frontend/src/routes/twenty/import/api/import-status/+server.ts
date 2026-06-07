import { env } from '$env/dynamic/private';
import type { RequestHandler } from './$types';

const API = env.BACKEND_API_URL || 'http://localhost:8000';

export const GET: RequestHandler = async ({ url, cookies }) => {
	const sessionId = cookies.get('sessionid');
	const headers: Record<string, string> = {};
	if (sessionId) headers['Cookie'] = `sessionid=${sessionId}`;

	const taskId = url.searchParams.get('task_id');

	const response = await fetch(
		`${API}/api/twenty/import-status?task_id=${taskId}`,
		{ method: 'GET', headers }
	);

	const json = await response.json();
	return new Response(JSON.stringify(json), {
		status: response.status,
		headers: { 'Content-Type': 'application/json' }
	});
};
