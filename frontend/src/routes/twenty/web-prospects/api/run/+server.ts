import { proxyPost } from '$lib/webprospects/proxy';
import type { RequestHandler } from './$types';

export const POST: RequestHandler = async ({ request, cookies }) => {
	const body = await request.json();
	return proxyPost('/run', body, cookies);
};
