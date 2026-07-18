import { proxyGet } from '$lib/webprospects/proxy';
import type { RequestHandler } from './$types';

export const GET: RequestHandler = async ({ cookies }) => {
	return proxyGet('/runs', cookies);
};
