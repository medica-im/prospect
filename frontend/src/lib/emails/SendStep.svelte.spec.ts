import { page, userEvent } from 'vitest/browser';
import { describe, expect, it } from 'vitest';
import { render } from 'vitest-browser-svelte';
import SendStep from './SendStep.svelte';

const recipientsJson = JSON.stringify([
	{ company_name: 'MSP du Marais', company_email: 'a@example.fr', company_type_id: 1, twenty_crm_id: 'c1' },
	{ company_name: 'CPTS Nord', company_email: 'b@example.fr', company_type_id: 2, twenty_crm_id: 'c2' }
]);

/** "YYYY-MM-DDTHH:MM" for `days` from now, as a datetime-local input wants it. */
function localInput(days: number): string {
	const d = new Date(Date.now() + days * 86_400_000);
	const pad = (n: number) => String(n).padStart(2, '0');
	return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

function setup(templateId: number | null = 7) {
	const submitted: Record<string, string>[] = [];
	render(SendStep, {
		formProps: {
			onsubmit: (event: SubmitEvent) => {
				event.preventDefault();
				const data = new FormData(event.currentTarget as HTMLFormElement);
				submitted.push(Object.fromEntries([...data].map(([k, v]) => [k, String(v)])));
			}
		},
		templateId,
		recipientsJson,
		count: 2,
		onback: () => {}
	});
	return submitted;
}

describe('SendStep.svelte', () => {
	it('sends immediately by default, without a schedule', async () => {
		const submitted = setup();

		await page.getByRole('button', { name: 'Send 2 Email(s)' }).click();

		await expect.poll(() => submitted.length).toBe(1);
		expect(submitted[0].template_id).toBe('7');
		expect(submitted[0].recipients).toBe(recipientsJson);
		expect(submitted[0].scheduled_for).toBe('');
	});

	it('schedules the batch once a date and time are picked', async () => {
		const submitted = setup();

		await page.getByRole('radio', { name: 'Schedule for later' }).click();
		const schedule = page.getByRole('button', { name: 'Schedule 2 Email(s)' });
		// Nothing picked yet, so the batch cannot be scheduled.
		await expect.element(schedule).toBeDisabled();

		const when = localInput(2);
		await page.getByLabelText('Date and time').fill(when);
		await expect.element(schedule).toBeEnabled();
		await expect.element(page.getByLabelText('Time zone')).toHaveValue('Europe/Paris');

		await schedule.click();

		await expect.poll(() => submitted.length).toBe(1);
		expect(submitted[0]).toMatchObject({
			template_id: '7',
			recipients: recipientsJson,
			scheduled_for: when,
			timezone: 'Europe/Paris'
		});
	});

	it('sends the zone the operator picked', async () => {
		const submitted = setup();

		await page.getByRole('radio', { name: 'Schedule for later' }).click();
		await page.getByLabelText('Date and time').fill(localInput(2));
		await page.getByLabelText('Time zone').selectOptions('America/Toronto');
		await page.getByRole('button', { name: 'Schedule 2 Email(s)' }).click();

		await expect.poll(() => submitted.length).toBe(1);
		expect(submitted[0].timezone).toBe('America/Toronto');
	});

	it('refuses a time in the past', async () => {
		const submitted = setup();

		await page.getByRole('radio', { name: 'Schedule for later' }).click();
		await page.getByLabelText('Date and time').fill(localInput(-2));

		await expect.element(page.getByText('Pick a time in the future.')).toBeInTheDocument();
		await expect
			.element(page.getByRole('button', { name: 'Schedule 2 Email(s)' }))
			.toBeDisabled();
		expect(submitted).toHaveLength(0);
	});

	it('cannot be sent without a template', async () => {
		setup(null);

		await expect.element(page.getByRole('button', { name: 'Send 2 Email(s)' })).toBeDisabled();
	});

	it('goes back when asked', async () => {
		let backed = false;
		render(SendStep, {
			formProps: {},
			templateId: 7,
			recipientsJson,
			count: 2,
			onback: () => (backed = true)
		});

		await userEvent.click(page.getByRole('button', { name: '← Back' }));

		expect(backed).toBe(true);
	});
});
