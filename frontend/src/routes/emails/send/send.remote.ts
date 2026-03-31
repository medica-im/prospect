import { env } from '$env/dynamic/private';
import { getRequestEvent, form } from '$app/server';
import * as z from 'zod';

const API = env.BACKEND_API_URL || 'http://localhost:8000';

const SendEmailPost = z.object({
	template_id: z.coerce.number(),
	recipients: z.preprocess((val) => JSON.parse(val as string), z.array(z.object({
		company_name: z.string(),
		company_email: z.string(),
		company_type_id: z.number(),
		twenty_crm_id: z.string(),
	}))),
});

export const sendEmails = form(SendEmailPost, async (data) => {
	const { cookies } = getRequestEvent();
	const sessionId = cookies.get('sessionid');
	const headers: Record<string, string> = { 'Content-Type': 'application/json' };
	if (sessionId) headers['Cookie'] = `sessionid=${sessionId}`;

	const response = await fetch(`${API}/api/emails/send`, {
		method: 'POST',
		headers,
		body: JSON.stringify(data),
	});

	if (!response.ok) {
		const text = await response.text();
		console.error(`Send emails failed: ${response.status} ${response.statusText}`);
		return { success: false, message: text };
	}

	const json = await response.json();
	return { success: true, message: json.message };
});
