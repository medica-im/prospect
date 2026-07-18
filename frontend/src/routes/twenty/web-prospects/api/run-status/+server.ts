import { proxyGet } from '$lib/webprospects/proxy';
import type { RequestHandler } from './$types';

export const GET: RequestHandler = async ({ url, cookies }) => {
	const taskId = url.searchParams.get('task_id') ?? '';
	return proxyGet(`/run-status?task_id=${encodeURIComponent(taskId)}`, cookies);
};
