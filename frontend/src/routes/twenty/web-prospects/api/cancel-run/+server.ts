import { proxyPost } from '$lib/webprospects/proxy';
import type { RequestHandler } from './$types';

export const POST: RequestHandler = async ({ url, cookies }) => {
	const taskId = url.searchParams.get('task_id') ?? '';
	return proxyPost(`/cancel-run?task_id=${encodeURIComponent(taskId)}`, {}, cookies);
};
