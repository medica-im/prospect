<script lang="ts">
	export type Person = { first_name: string; last_name: string };
	export type MspRecord = {
		name: string;
		address_line1: string;
		postcode: string;
		city: string;
		finess_number: string;
		finess_date: string;
		project_type: string;
		coordinators: Person[];
		team_leaders: Person[];
		email: string;
		phone: string;
		website: string;
	};

	let {
		record = $bindable(),
		missingFields = [],
		existingCount = 0,
		index,
		total,
		busy = false,
		onConfirm,
		onSkip
	}: {
		record: MspRecord;
		missingFields?: string[];
		existingCount?: number;
		index: number;
		total: number;
		busy?: boolean;
		onConfirm: () => void;
		onSkip: () => void;
	} = $props();

	function isMissing(field: string): boolean {
		return missingFields.includes(field);
	}

	function addCoordinator() {
		record.coordinators = [...record.coordinators, { first_name: '', last_name: '' }];
	}
	function addTeamLeader() {
		record.team_leaders = [...record.team_leaders, { first_name: '', last_name: '' }];
	}
	function removeCoordinator(i: number) {
		record.coordinators = record.coordinators.filter((_, j) => j !== i);
	}
	function removeTeamLeader(i: number) {
		record.team_leaders = record.team_leaders.filter((_, j) => j !== i);
	}
</script>

<div class="card p-6 space-y-4">
	<header class="flex items-center justify-between">
		<h3 class="h4">
			Card {index + 1} / {total}
		</h3>
		{#if existingCount === 1}
			<span class="badge preset-filled-warning-500 text-xs">Already in Twenty</span>
		{:else if existingCount > 1}
			<span class="badge preset-filled-error-500 text-xs">{existingCount} matches in Twenty</span>
		{/if}
	</header>

	<label class="label">
		<span class="flex items-center gap-2">
			Name {#if isMissing('name')}<span class="text-error-500 text-xs">(missing)</span>{/if}
		</span>
		<input class="input" bind:value={record.name} />
	</label>

	<div class="grid grid-cols-1 md:grid-cols-3 gap-3">
		<label class="label md:col-span-3">
			<span>Address</span>
			<input class="input" bind:value={record.address_line1} />
		</label>
		<label class="label">
			<span>Postcode</span>
			<input class="input" bind:value={record.postcode} />
		</label>
		<label class="label md:col-span-2">
			<span>City</span>
			<input class="input" bind:value={record.city} />
		</label>
	</div>

	<div class="grid grid-cols-1 md:grid-cols-3 gap-3">
		<label class="label">
			<span>Numéro Finess</span>
			<input class="input" bind:value={record.finess_number} />
		</label>
		<label class="label">
			<span>Date Finess</span>
			<input class="input" bind:value={record.finess_date} />
		</label>
		<label class="label">
			<span>Type de projet</span>
			<input class="input" bind:value={record.project_type} />
		</label>
	</div>

	<div class="grid grid-cols-1 md:grid-cols-3 gap-3">
		<label class="label">
			<span class="flex items-center gap-2">
				Email {#if isMissing('email')}<span class="text-error-500 text-xs">(missing)</span>{/if}
			</span>
			<input class="input" bind:value={record.email} />
		</label>
		<label class="label">
			<span>Phone</span>
			<input class="input" bind:value={record.phone} />
		</label>
		<label class="label">
			<span>Website (domain)</span>
			<input class="input" bind:value={record.website} />
		</label>
	</div>

	<!-- Coordinators -->
	<div class="space-y-2">
		<div class="flex items-center justify-between">
			<span class="font-semibold text-sm">Coordinateur(s)</span>
			<button type="button" class="btn btn-sm preset-tonal" onclick={addCoordinator}>+ Add</button>
		</div>
		{#each record.coordinators as person, i (i)}
			<div class="flex gap-2 items-center">
				<input class="input" placeholder="First name" bind:value={person.first_name} />
				<input class="input" placeholder="Last name" bind:value={person.last_name} />
				<button type="button" class="btn btn-sm preset-tonal-error" onclick={() => removeCoordinator(i)}>✕</button>
			</div>
		{/each}
	</div>

	<!-- Team leaders -->
	<div class="space-y-2">
		<div class="flex items-center justify-between">
			<span class="font-semibold text-sm">Team Leader(s)</span>
			<button type="button" class="btn btn-sm preset-tonal" onclick={addTeamLeader}>+ Add</button>
		</div>
		{#each record.team_leaders as person, i (i)}
			<div class="flex gap-2 items-center">
				<input class="input" placeholder="First name" bind:value={person.first_name} />
				<input class="input" placeholder="Last name" bind:value={person.last_name} />
				<button type="button" class="btn btn-sm preset-tonal-error" onclick={() => removeTeamLeader(i)}>✕</button>
			</div>
		{/each}
	</div>

	<footer class="flex gap-3 pt-2">
		<button class="btn preset-filled-primary-500" disabled={busy} onclick={onConfirm}>
			{busy ? 'Creating…' : 'Confirm & Create'}
		</button>
		<button class="btn preset-outlined-surface-500" disabled={busy} onclick={onSkip}>
			Skip
		</button>
	</footer>
</div>
