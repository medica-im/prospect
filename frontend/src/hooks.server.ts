import { sequence } from '@sveltejs/kit/hooks';
import { env } from '$env/dynamic/private';
import type { Handle } from '@sveltejs/kit';
import { getTextDirection } from '$lib/paraglide/runtime';
import { paraglideMiddleware } from '$lib/paraglide/server';

const API = env.BACKEND_API_URL || 'http://localhost:8000';

const handleParaglide: Handle = ({ event, resolve }) => paraglideMiddleware(event.request, ({ request, locale }) => {
	event.request = request;

	return resolve(event, {
		transformPageChunk: ({ html }) => html.replace('%paraglide.lang%', locale).replace('%paraglide.dir%', getTextDirection(locale))
	});
});

const handleAuth: Handle = async ({ event, resolve }) => {
	const sessionId = event.cookies.get('sessionid');

	if (sessionId) {
		try {
			const response = await fetch(`${API}/api/auth/me`, {
				headers: { Cookie: `sessionid=${sessionId}` }
			});
			if (response.ok) {
				event.locals.user = await response.json();
			}
		} catch {
			// Django unreachable — treat as unauthenticated
		}
	}

	return resolve(event);
};

export const handle: Handle = sequence(handleParaglide, handleAuth);
