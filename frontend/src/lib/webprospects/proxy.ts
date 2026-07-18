import { env } from '$env/dynamic/private';
import type { Cookies } from '@sveltejs/kit';

const API = env.BACKEND_API_URL || 'http://localhost:8000';

function authHeaders(cookies: Cookies, json = false): Record<string, string> {
	const headers: Record<string, string> = {};
	if (json) headers['Content-Type'] = 'application/json';
	const sessionId = cookies.get('sessionid');
	if (sessionId) headers['Cookie'] = `sessionid=${sessionId}`;
	return headers;
}

export async function proxyGet(path: string, cookies: Cookies): Promise<Response> {
	const response = await fetch(`${API}/api/webprospects${path}`, {
		headers: authHeaders(cookies)
	});
	const text = await response.text();
	return new Response(text, {
		status: response.status,
		headers: { 'Content-Type': 'application/json' }
	});
}

export async function proxyPost(path: string, body: unknown, cookies: Cookies): Promise<Response> {
	const response = await fetch(`${API}/api/webprospects${path}`, {
		method: 'POST',
		headers: authHeaders(cookies, true),
		body: JSON.stringify(body)
	});
	const text = await response.text();
	return new Response(text, {
		status: response.status,
		headers: { 'Content-Type': 'application/json' }
	});
}
