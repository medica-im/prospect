<script lang="ts">
	import { resolve } from '$app/paths';
	import { TONE_CLASS } from '$lib/emails/delivery';
	import {
		ACTION_OPTIONS,
		ACTION_TONE,
		REASON_LABEL,
		WHERE_LABEL,
		companyTypes,
		countByAction,
		countByKind,
		filterProblems,
		formatDate,
		formatDateTime,
		problemKind,
		problemLabel,
		type ActionFilter
	} from '$lib/emails/problems';
	import type { PageData } from './$types';

	let { data }: { data: PageData } = $props();

	let rows = $derived(data.problems?.rows ?? []);

	let search = $state('');
	// Opens on what to delete from Twenty: the page's reason for being.
	let action = $state<ActionFilter>('remove');
	let kind = $state('');
	let companyType = $state('');

	let actionCounts = $derived(countByAction(rows));
	// Counted within the chosen action so the numbers add up with the table.
	let kindCounts = $derived(
		countByKind(filterProblems(rows, { action, kind: '', companyType: '', search: '' }))
	);
	let types = $derived(companyTypes(rows));
	let filtered = $derived(filterProblems(rows, { action, kind, companyType, search }));
	let hint = $derived(ACTION_OPTIONS.find((option) => option.value === action)?.hint ?? '');

	function setAction(value: ActionFilter) {
		action = value;
		kind = '';
	}
</script>

<svelte:head>
	<title>Adresses à problème</title>
</svelte:head>

<div class="mb-2 flex flex-col items-start justify-between gap-4 sm:flex-row sm:items-center">
	<h1 class="h3">Adresses à problème ({filtered.length})</h1>
	<div class="flex flex-wrap items-center gap-3">
		<!-- A plain link: the proxy route streams the file back as a download. -->
		<a
			class="btn preset-filled-primary-500"
			href={resolve(`/emails/problems/current-problems.csv?action=${action}`)}
			download
		>
			Télécharger (CSV)
		</a>
		<!-- ?refresh=1 re-reads Twenty, then the load function redirects back here. -->
		<a
			class="btn preset-outlined-surface-500"
			href={resolve('/emails/problems?refresh=1')}
			data-sveltekit-reload
		>
			Rafraîchir depuis Twenty
		</a>
	</div>
</div>

{#if data.problems === null}
	<div class="card preset-tonal-error p-4" role="alert">
		{data.status === 502
			? "Twenty n'a pas répondu. Réessayez dans un instant."
			: `Impossible de charger la liste (erreur ${data.status}).`}
	</div>
{:else}
	<p class="mb-6 text-sm text-surface-600-400">
		Adresses présentes dans Twenty dont le dernier envoi n'a pas abouti, avec ce qu'il convient d'en
		faire. Lecture de Twenty du
		{formatDateTime(data.problems.snapshot_at)} (mise en cache dix minutes). Les corrections se font dans
		Twenty.
	</p>

	<div class="mb-2 flex flex-wrap gap-2" role="group" aria-label="Que faire">
		{#each ACTION_OPTIONS as option (option.value)}
			<button
				type="button"
				class="btn btn-sm {action === option.value
					? 'preset-filled-primary-500'
					: 'preset-outlined-surface-500'}"
				aria-pressed={action === option.value}
				onclick={() => setAction(option.value)}
			>
				{option.label} ({actionCounts[option.value]})
			</button>
		{/each}
	</div>
	<p class="mb-3 min-h-5 text-sm text-surface-600-400">{hint}</p>

	<div class="mb-6 flex flex-wrap gap-2" role="group" aria-label="Type de problème">
		<button
			type="button"
			class="btn btn-sm {kind === ''
				? 'preset-filled-secondary-500'
				: 'preset-outlined-surface-500'}"
			aria-pressed={kind === ''}
			onclick={() => (kind = '')}
		>
			Tous les problèmes
		</button>
		{#each kindCounts as entry (entry.kind)}
			<button
				type="button"
				class="btn btn-sm {kind === entry.kind
					? 'preset-filled-secondary-500'
					: 'preset-outlined-surface-500'}"
				aria-pressed={kind === entry.kind}
				onclick={() => (kind = entry.kind)}
			>
				{entry.label} ({entry.count})
			</button>
		{/each}
	</div>

	<div class="mb-6 flex flex-col gap-3 sm:flex-row">
		<input
			type="search"
			placeholder="Rechercher une adresse, une structure ou une personne..."
			class="input flex-1"
			bind:value={search}
		/>
		<select class="select sm:w-48" bind:value={companyType} aria-label="Type de structure">
			<option value="">Tous les types</option>
			{#each types as type (type)}
				<option value={type}>{type}</option>
			{/each}
		</select>
	</div>

	{#if filtered.length === 0}
		<div class="card p-6 text-center text-surface-500">Aucune adresse à problème.</div>
	{:else}
		<div class="table-wrap">
			<table class="table">
				<thead>
					<tr>
						<th>Adresse</th>
						<th>Personne</th>
						<th>Structure</th>
						<th>Que faire</th>
						<th>Problème</th>
						<th>Détail du serveur</th>
						<th class="text-right">Envois</th>
						<th>Premier envoi</th>
						<th>Début du problème</th>
						<th>Dernier envoi</th>
						<th></th>
					</tr>
				</thead>
				<tbody>
					{#each filtered as row (`${row.address}|${row.where}|${row.person_id || row.company_id}`)}
						<tr>
							<td class="break-all">
								{row.address}
								<div class="text-xs text-surface-600-400">{WHERE_LABEL[row.where]}</div>
							</td>
							<td>
								{row.person_name}
								{#if row.job_title}
									<div class="text-xs text-surface-600-400">{row.job_title}</div>
								{/if}
							</td>
							<td>
								{row.company_name}
								{#if row.company_type}
									<div class="text-xs text-surface-600-400">{row.company_type}</div>
								{/if}
							</td>
							<td>
								<span
									class="badge {TONE_CLASS[ACTION_TONE[row.action]]} text-xs whitespace-nowrap"
									data-action={row.action}
								>
									{ACTION_OPTIONS.find((option) => option.value === row.action)?.label}
								</span>
								<div class="mt-1 text-xs text-surface-600-400">
									{REASON_LABEL[row.reason] ?? row.reason}
								</div>
							</td>
							<td>
								<span class="text-sm whitespace-nowrap" data-kind={problemKind(row)}>
									{problemLabel(row)}
								</span>
							</td>
							<td class="max-w-xs text-sm break-words">{row.smtp_detail}</td>
							<td class="text-right">{row.attempts}</td>
							<td class="whitespace-nowrap">{formatDate(row.first_sent_at)}</td>
							<td class="whitespace-nowrap">{formatDate(row.first_problem_at)}</td>
							<td class="whitespace-nowrap">{formatDate(row.last_attempt_at)}</td>
							<td>
								<!-- Twenty lives on another origin; resolve() is for this app's own routes. -->
								<!-- eslint-disable-next-line svelte/no-navigation-without-resolve -->
								<a class="anchor" href={row.twenty_url} target="_blank" rel="noopener noreferrer">
									Twenty
								</a>
							</td>
						</tr>
					{/each}
				</tbody>
			</table>
		</div>
	{/if}
{/if}
