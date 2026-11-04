<script lang="ts">
	import type { HTMLFormAttributes } from 'svelte/elements';
	import {
		DEFAULT_TIME_ZONE,
		inBrowserZone,
		timeZones,
		wallClockToInstant
	} from './schedule';

	let {
		formProps,
		templateId,
		recipientsJson,
		count,
		pending = false,
		onback
	}: {
		// Spread on the <form>: the remote form's enhance() in the page, a plain
		// onsubmit handler in tests.
		formProps: HTMLFormAttributes;
		templateId: number | null;
		recipientsJson: string;
		count: number;
		pending?: boolean;
		onback: () => void;
	} = $props();

	// The time is a wall clock in the chosen zone (the operator's clients are in
	// Paris, the operator is not); the backend converts it.
	let sendLater = $state(false);
	let scheduledFor = $state('');
	let timeZone = $state(DEFAULT_TIME_ZONE);
	const zones = timeZones();

	let scheduledInstant = $derived(sendLater ? wallClockToInstant(scheduledFor, timeZone) : null);
	let scheduleError = $derived.by(() => {
		if (!sendLater) return '';
		if (!scheduledFor) return 'Pick a date and time.';
		if (!scheduledInstant) return 'This time does not exist in that zone (clocks change).';
		if (scheduledInstant.getTime() < Date.now() + 60_000) return 'Pick a time in the future.';
		return '';
	});
</script>

<form {...formProps} class="space-y-3">
	<fieldset class="card p-4 space-y-3">
		<legend class="font-bold px-2">When</legend>
		<label class="flex items-center gap-2">
			<input
				type="radio"
				name="when"
				class="radio"
				checked={!sendLater}
				onchange={() => (sendLater = false)}
			/>
			Send now
		</label>
		<label class="flex items-center gap-2">
			<input
				type="radio"
				name="when"
				class="radio"
				checked={sendLater}
				onchange={() => (sendLater = true)}
			/>
			Schedule for later
		</label>

		{#if sendLater}
			<div class="flex flex-wrap items-end gap-3">
				<label class="label">
					<span class="label-text">Date and time</span>
					<input type="datetime-local" class="input" bind:value={scheduledFor} />
				</label>
				<label class="label">
					<span class="label-text">Time zone</span>
					<select class="select" bind:value={timeZone}>
						{#each zones as zone (zone)}
							<option value={zone}>{zone}</option>
						{/each}
					</select>
				</label>
			</div>
			{#if scheduleError}
				<p class="text-sm text-error-500">{scheduleError}</p>
			{:else if scheduledInstant}
				<p class="text-sm text-surface-600-400">
					That is {inBrowserZone(scheduledInstant)} for you.
				</p>
			{/if}
		{/if}
	</fieldset>

	<input type="hidden" name="template_id" value={templateId ?? ''} />
	<input type="hidden" name="recipients" value={recipientsJson} />
	<input type="hidden" name="scheduled_for" value={sendLater ? scheduledFor : ''} />
	<input type="hidden" name="timezone" value={timeZone} />

	<div class="flex justify-between">
		<button type="button" class="btn preset-outlined-surface-500" onclick={onback}>
			← Back
		</button>
		<button
			type="submit"
			class="btn preset-filled-primary-500"
			disabled={templateId === null || pending || !!scheduleError}
		>
			{#if pending}
				{sendLater ? 'Scheduling...' : 'Sending...'}
			{:else if sendLater}
				Schedule {count} Email(s)
			{:else}
				Send {count} Email(s)
			{/if}
		</button>
	</div>
</form>
