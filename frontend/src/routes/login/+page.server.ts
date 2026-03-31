import { env } from '$env/dynamic/private';
import { fail, redirect } from '@sveltejs/kit';
import type { Actions, PageServerLoad } from './$types';

const API = env.BACKEND_API_URL || 'http://localhost:8000';

export const load: PageServerLoad = async ({ locals }) => {
	if (locals.user) {
		redirect(302, '/emails/send');
	}
};

export const actions: Actions = {
	default: async ({ request, cookies }) => {
		const formData = await request.formData();
		const username = formData.get('username') as string;
		const password = formData.get('password') as string;

		if (!username || !password) {
			return fail(400, { error: 'Username and password are required.' });
		}

		const response = await fetch(`${API}/api/auth/login`, {
			method: 'POST',
			headers: { 'Content-Type': 'application/json' },
			body: JSON.stringify({ username, password })
		});

		if (!response.ok) {
			return fail(401, { error: 'Invalid username or password.' });
		}

		// Forward Django session cookie to browser
		const setCookieHeader = response.headers.get('set-cookie');
		if (setCookieHeader) {
			for (const cookie of setCookieHeader.split(',')) {
				const parts = cookie.trim().split(';');
				const [nameValue] = parts;
				const [name, ...valueParts] = nameValue.split('=');
				const value = valueParts.join('=');
				if (name.trim() === 'sessionid') {
					cookies.set('sessionid', value, {
						path: '/',
						httpOnly: true,
						sameSite: 'lax',
						maxAge: 60 * 60 * 24 * 30
					});
				}
			}
		}

		redirect(303, '/emails/send');
	}
};
