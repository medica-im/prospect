// See https://svelte.dev/docs/kit/types#app.d.ts
// for information about these interfaces
declare global {
	namespace App {
		interface Locals {
			user?: { username: string; email: string };
		}

		// interface Error {}
		// interface PageData {}
		interface PageState {
			/** Send page wizard step, pushed as a shallow history entry. */
			step?: 1 | 2;
		}
		// interface Platform {}
	}
}

export {};
