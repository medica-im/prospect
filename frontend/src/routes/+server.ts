import { redirect } from '@sveltejs/kit';
import type { RequestHandler } from './$types';

// There is no home page: the app is the send page. A logged-out visitor lands on
// /login from there (see +layout.server.ts).
export const GET: RequestHandler = () => redirect(302, '/emails/send');
