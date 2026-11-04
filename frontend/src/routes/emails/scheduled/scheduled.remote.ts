import { env } from '$env/dynamic/private';
import { getRequestEvent, form } from '$app/server';
import * as z from 'zod';

const API = env.BACKEND_API_URL || 'http://localhost:8000';

const CancelPost = z.object({
	id: z.string().transform((v) => Number(v))
});

export const cancelBatch = form(CancelPost, async ({ id }) => {
	const { cookies } = getRequestEvent();
	const sessionId = cookies.get('sessionid');
	const headers: Record<string, string> = {};
	if (sessionId) headers['Cookie'] = `sessionid=${sessionId}`;

	const response = await fetch(`${API}/api/emails/scheduled/${id}/cancel`, {
		method: 'POST',
		headers
	});
	if (!response.ok) {
		console.error(`Cancel batch ${id} failed: ${response.status} ${response.statusText}`);
		return { success: false, message: await response.text() };
	}
	return { success: true, message: 'Batch cancelled.' };
});
