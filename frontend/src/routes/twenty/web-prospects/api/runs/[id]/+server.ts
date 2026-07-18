import { proxyGet } from '$lib/webprospects/proxy';
import type { RequestHandler } from './$types';

export const GET: RequestHandler = async ({ params, cookies }) => {
	return proxyGet(`/runs/${params.id}`, cookies);
};
