<script lang="ts">
	import MspCard, { type MspRecord } from '$lib/webprospects/MspCard.svelte';
	import ReportTable, { type ReportRow } from '$lib/webprospects/ReportTable.svelte';
	import type { PageData } from './$types';

	let { data }: { data: PageData } = $props();

	type DiffEntry = { field: string; label: string; value: string; target: string };
	type ScrapedRecord = {
		record: MspRecord;
		missing_fields: string[];
		existing_count: number;
		existing_ids: string[];
		missing_essential: DiffEntry[];
	};

	// --- Form state ---
	let url = $state('');
	let askConfirmation = $state(true);
	let setCompanyType = $state(true);

	// --- Flow state ---
	let phase = $state<'idle' | 'scraping' | 'confirming' | 'running' | 'done'>('idle');
	let error = $state('');
	let suggestion = $derived(
		url.replace(/^https?:\/\//, '').replace(/^www\./, '').startsWith('apmsl.fr')
			? 'apmsl'
			: null
	);

	// --- Confirmation flow ---
	let scraped = $state<ScrapedRecord[]>([]);
	let ambiguous = $state(false);
	let cancelledAmbiguous = $state(false);
	let currentIndex = $state(0);
	let runId = $state<number | null>(null);
	let cardBusy = $state(false);
	let sourceUrl = $state('');
	let reportRows = $state<ReportRow[]>([]);

	// --- Update-existing popup ---
	let updateDialog = $state<HTMLDialogElement | null>(null);
	let updateDiff = $state<DiffEntry[]>([]);
	let updateCompanyId = $state('');
	let updateBusy = $state(false);
	let nothingMissing = $state(false);

	// --- Direct run flow ---
	let runProgress = $state({ processed: 0, total: 0, created: 0, updated: 0, already_present: 0, skipped: 0, failed: 0 });
	let pollTimer: ReturnType<typeof setInterval> | null = null;
	let runTaskId = $state('');
	let cancelling = $state(false);
	let pendingTicks = 0;

	let currentCard = $derived(scraped[currentIndex]);

	function reset() {
		phase = 'idle';
		error = '';
		scraped = [];
		ambiguous = false;
		cancelledAmbiguous = false;
		currentIndex = 0;
		runId = null;
		reportRows = [];
		runTaskId = '';
		cancelling = false;
		updateDiff = [];
		updateCompanyId = '';
		nothingMissing = false;
		if (pollTimer) clearInterval(pollTimer);
		pollTimer = null;
	}

	// Read a response as JSON, tolerating non-JSON (e.g. an HTML error page from a
	// proxy/gateway) so we surface a readable message instead of a raw
	// "Unexpected token '<'" JSON parse error.
	async function readJson(res: Response): Promise<any> {
		const text = await res.text();
		try {
			return JSON.parse(text);
		} catch {
			if (!res.ok) {
				return { detail: `Server error (HTTP ${res.status}). Please try again.` };
			}
			return {};
		}
	}

	async function start() {
		error = '';
		reportRows = [];
		if (!url.trim()) {
			error = 'Please enter a URL.';
			return;
		}
		if (askConfirmation) {
			await scrape();
		} else {
			await runAll();
		}
	}

	async function scrape() {
		error = '';
		phase = 'scraping';
		try {
			const res = await fetch('/twenty/web-prospects/api/scrape', {
				method: 'POST',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify({ url, scraper: suggestion })
			});
			const json = await readJson(res);
			if (!res.ok) {
				error = json.detail || 'Scrape failed';
				phase = 'idle';
				return;
			}
			scraped = json.records;
			ambiguous = json.ambiguous;
			sourceUrl = json.source_url;
			currentIndex = 0;
			runId = null;
			phase = 'confirming';
		} catch (e) {
			error = String(e);
			phase = 'idle';
		}
	}

	async function confirmCurrent() {
		if (!currentCard) return;
		error = '';
		cardBusy = true;
		try {
			const res = await fetch('/twenty/web-prospects/api/create-one', {
				method: 'POST',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify({
					run_id: runId,
					source_url: sourceUrl,
					record: currentCard.record,
					set_company_type: setCompanyType,
					skip_if_exists: true
				})
			});
			const json = await readJson(res);
			if (!res.ok) {
				error = json.detail || 'Create failed';
				cardBusy = false;
				return;
			}
			runId = json.run_id;
			reportRows = [
				...reportRows,
				{
					name: currentCard.record.name,
					status: json.status,
					twenty_company_id: json.twenty_company_id,
					missing_fields: json.missing_fields,
					error: json.error,
					duplicate_company_id: json.duplicate_company_id,
					duplicate_company_name: json.duplicate_company_name
				}
			];
			advance();
		} catch (e) {
			error = String(e);
		} finally {
			cardBusy = false;
		}
	}

	function skipCurrent() {
		if (!currentCard) return;
		error = '';
		reportRows = [
			...reportRows,
			{ name: currentCard.record.name, status: 'skipped', missing_fields: currentCard.missing_fields }
		];
		advance();
	}

	function advance() {
		if (currentIndex + 1 >= scraped.length) {
			phase = 'done';
		} else {
			currentIndex += 1;
		}
	}

	// The MSP already exists and (from the scrape-time check) has missing essential
	// data. Open the popup listing exactly what would be added before confirming.
	function openUpdate() {
		if (!currentCard) return;
		error = '';
		updateCompanyId = currentCard.existing_ids[0] ?? '';
		updateDiff = currentCard.missing_essential ?? [];
		nothingMissing = updateDiff.length === 0;
		updateDialog?.showModal();
	}

	function targetLabel(target: string): string {
		return target === 'company' ? 'company record' : 'a new “Contact” person';
	}

	function closeUpdate() {
		updateDialog?.close();
	}

	async function confirmUpdate() {
		if (!currentCard) return;
		updateBusy = true;
		try {
			const res = await fetch('/twenty/web-prospects/api/update-existing', {
				method: 'POST',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify({
					run_id: runId,
					source_url: sourceUrl,
					company_id: updateCompanyId,
					record: currentCard.record
				})
			});
			const json = await readJson(res);
			if (!res.ok) {
				error = json.detail || 'Update failed';
				return;
			}
			runId = json.run_id;
			reportRows = [
				...reportRows,
				{
					name: currentCard.record.name,
					status: json.status,
					twenty_company_id: json.twenty_company_id,
					missing_fields: json.updated_fields,
					error: json.error,
					duplicate_company_id: json.duplicate_company_id,
					duplicate_company_name: json.duplicate_company_name
				}
			];
			closeUpdate();
			advance();
		} catch (e) {
			error = String(e);
		} finally {
			updateBusy = false;
		}
	}

	// --- Direct run (no confirmation) ---
	async function runAll() {
		error = '';
		phase = 'running';
		pendingTicks = 0;
		runProgress = { processed: 0, total: 0, created: 0, updated: 0, already_present: 0, skipped: 0, failed: 0 };
		try {
			const res = await fetch('/twenty/web-prospects/api/run', {
				method: 'POST',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify({
					url,
					scraper: suggestion,
					set_company_type: setCompanyType,
					skip_if_exists: true
				})
			});
			const json = await readJson(res);
			if (!res.ok) {
				error = json.detail || 'Run failed';
				phase = 'idle';
				return;
			}
			runTaskId = json.task_id;
			pollTimer = setInterval(() => pollRun(json.task_id), 2000);
		} catch (e) {
			error = String(e);
			phase = 'idle';
		}
	}

	// Cancel the automatic (Celery) run: stop it server-side, keep polling so the
	// UI settles on the finalized (partial) report the task writes on cancel.
	async function cancelRun() {
		if (!runTaskId) return;
		cancelling = true;
		try {
			await fetch(`/twenty/web-prospects/api/cancel-run?task_id=${encodeURIComponent(runTaskId)}`, {
				method: 'POST'
			});
		} catch (e) {
			console.error('cancel error', e);
		}
	}

	// Cancel the confirmation flow: stop reviewing remaining cards and show the
	// report of what was already created/skipped.
	function cancelConfirming() {
		phase = 'done';
	}

	async function pollRun(taskId: string) {
		try {
			const res = await fetch(`/twenty/web-prospects/api/run-status?task_id=${encodeURIComponent(taskId)}`);
			const json = await readJson(res);
			if (json.state === 'PROGRESS') {
				pendingTicks = 0;
				runProgress = {
					processed: json.processed ?? 0,
					total: json.total ?? 0,
					created: json.created ?? 0,
					updated: json.updated ?? 0,
					already_present: json.already_present ?? 0,
					skipped: json.skipped ?? 0,
					failed: json.failed ?? 0
				};
			} else if (json.state === 'SUCCESS') {
				if (pollTimer) clearInterval(pollTimer);
				runId = json.run_id;
				await loadRunReport(json.run_id);
				phase = 'done';
			} else if (json.state === 'FAILED') {
				if (pollTimer) clearInterval(pollTimer);
				error = json.error || 'Run failed';
				phase = 'idle';
			} else {
				// PENDING/unknown: the task hasn't been picked up yet. Give the
				// worker a bounded grace period, then stop rather than poll forever
				// (e.g. the Celery worker is down).
				pendingTicks += 1;
				if (pendingTicks > 15) {
					if (pollTimer) clearInterval(pollTimer);
					error =
						'The run task was not picked up by a worker (still pending after 30s). ' +
						'Is the Celery worker running?';
					phase = 'idle';
				}
			}
		} catch (e) {
			console.error('poll error', e);
		}
	}

	async function loadRunReport(id: number) {
		const res = await fetch(`/twenty/web-prospects/api/runs/${id}`);
		if (res.ok) {
			const json = await res.json();
			reportRows = json.records;
		}
	}

	let progressPercent = $derived(
		runProgress.total > 0 ? Math.round((runProgress.processed / runProgress.total) * 100) : 0
	);
</script>

<svelte:head>
	<title>Web Prospects</title>
</svelte:head>

<h1 class="h3 mb-6">Web Prospects → Twenty CRM</h1>

{#if phase === 'idle' || phase === 'scraping' || phase === 'running'}
	<div class="card p-6 space-y-4 mb-6">
		<label class="label">
			<span>Page URL</span>
			<input
				class="input"
				placeholder="https://www.apmsl.fr/..."
				bind:value={url}
				disabled={phase !== 'idle'}
			/>
		</label>

		{#if suggestion === 'apmsl'}
			<aside class="alert preset-tonal-primary">
				<p class="text-sm">apmsl.fr detected — the <strong>apmsl</strong> scraper will be used.</p>
			</aside>
		{/if}

		<div class="flex flex-wrap gap-6">
			<label class="flex items-center gap-2">
				<input class="checkbox" type="checkbox" bind:checked={askConfirmation} disabled={phase !== 'idle'} />
				<span>Ask for confirmation (review each card before creating)</span>
			</label>
			<label class="flex items-center gap-2">
				<input class="checkbox" type="checkbox" bind:checked={setCompanyType} disabled={phase !== 'idle'} />
				<span>Set company type to MSP</span>
			</label>
		</div>

		<button class="btn preset-filled-primary-500" onclick={start} disabled={phase !== 'idle'}>
			{#if phase === 'scraping'}Scraping…{:else if phase === 'running'}Starting…{:else}Scrape page{/if}
		</button>
	</div>
{/if}

{#if error}
	<aside class="alert preset-filled-error-500 mb-6 flex items-start justify-between gap-3">
		<p>{error}</p>
		<button
			class="btn-icon btn-icon-sm preset-tonal shrink-0"
			onclick={() => (error = '')}
			title="Dismiss"
			aria-label="Dismiss error"
		>
			✕
		</button>
	</aside>
{/if}

<!-- Confirmation flow -->
{#if phase === 'confirming'}
	{#if ambiguous && !cancelledAmbiguous}
		<aside class="alert preset-filled-warning-500 mb-6 space-y-3">
			<p>
				One or more MSP on this page match <strong>more than one</strong> company already in
				Twenty CRM. This may indicate duplicates.
			</p>
			<div class="flex gap-3">
				<button class="btn preset-filled-surface-500" onclick={reset}>Cancel</button>
				<button class="btn preset-outlined-surface-500" onclick={() => (cancelledAmbiguous = true)}>
					Proceed anyway
				</button>
			</div>
		</aside>
	{:else}
		<div class="mb-4 flex items-center justify-between gap-3">
			<span class="text-sm text-surface-500">
				{scraped.length} MSP found. Reviewing card {currentIndex + 1} of {scraped.length}.
			</span>
			<button class="btn btn-sm preset-outlined-error-500" onclick={cancelConfirming}>
				Cancel review
			</button>
		</div>
		{#if currentCard}
			<MspCard
				bind:record={scraped[currentIndex].record}
				missingFields={currentCard.missing_fields}
				existingCount={currentCard.existing_count}
				missingEssentialCount={currentCard.missing_essential.length}
				existingUrl={data.twentyBaseUrl && currentCard.existing_ids[0]
					? `${data.twentyBaseUrl}/object/company/${currentCard.existing_ids[0]}`
					: ''}
				index={currentIndex}
				total={scraped.length}
				busy={cardBusy}
				onConfirm={confirmCurrent}
				onSkip={skipCurrent}
				onUpdate={openUpdate}
			/>
		{/if}
		{#if reportRows.length > 0}
			<div class="mt-6">
				<ReportTable rows={reportRows} title="Processed so far" twentyBaseUrl={data.twentyBaseUrl} />
			</div>
		{/if}
	{/if}
{/if}

<!-- Direct run progress -->
{#if phase === 'running'}
	<div class="card p-6 text-center space-y-4">
		<p class="text-lg font-bold">Creating MSP in Twenty CRM…</p>
		{#if runProgress.total > 0}
			<div class="w-full bg-surface-200 rounded-full h-4 overflow-hidden">
				<div class="bg-primary-500 h-4 rounded-full transition-all" style="width: {progressPercent}%"></div>
			</div>
			<p class="text-sm text-surface-500">
				{runProgress.processed} / {runProgress.total} ({progressPercent}%)
			</p>
			<div class="flex justify-center gap-6 text-sm">
				<span class="text-green-600">{runProgress.created} created</span>
				<span class="text-blue-600">{runProgress.updated} updated</span>
				<span class="text-yellow-600">{runProgress.already_present} already present</span>
				<span class="text-red-600">{runProgress.failed} failed</span>
			</div>
		{:else}
			<p class="text-surface-500">Starting…</p>
		{/if}
		<div class="pt-2">
			<button class="btn preset-outlined-error-500" onclick={cancelRun} disabled={cancelling || !runTaskId}>
				{cancelling ? 'Cancelling…' : 'Cancel run'}
			</button>
			{#if cancelling}
				<p class="text-xs text-surface-500 mt-2">
					Finishing the current record, then stopping. The report will show what was created.
				</p>
			{/if}
		</div>
	</div>
{/if}

<!-- Done -->
{#if phase === 'done'}
	<div class="space-y-6">
		<aside class="alert preset-filled-success-500">
			<p>
				Done. {reportRows.filter((r) => r.status === 'created').length} created,
				{reportRows.filter((r) => r.status === 'updated').length} updated.
			</p>
		</aside>
		<ReportTable rows={reportRows} title="Report" twentyBaseUrl={data.twentyBaseUrl} />
		<button class="btn preset-filled-primary-500" onclick={reset}>Process another page</button>
	</div>
{/if}

<!-- Update-existing confirmation popup -->
<dialog
	bind:this={updateDialog}
	class="rounded-container backdrop:bg-surface-950/50 p-0 max-w-lg w-full"
	onclose={() => (updateDiff = [])}
>
	<div class="card p-6 space-y-4">
		<h3 class="h4">Update existing MSP in Twenty</h3>
		{#if nothingMissing}
			<p class="text-surface-600">
				This MSP already exists in Twenty and has all the essential data (email, phone,
				domain, address). Nothing to add.
			</p>
			<footer class="flex justify-end gap-3 pt-2">
				<button class="btn preset-filled-primary-500" onclick={closeUpdate}>Close</button>
			</footer>
		{:else}
			<p class="text-surface-600">
				This MSP already exists. The following data is missing and will be added to Twenty:
			</p>
			<ul class="space-y-2">
				{#each updateDiff as d (d.field)}
					<li class="flex flex-col rounded bg-surface-100-900 p-3">
						<span class="text-sm font-semibold">{d.label}</span>
						<span class="break-words">{d.value}</span>
						<span class="text-xs text-surface-500">→ added to {targetLabel(d.target)}</span>
					</li>
				{/each}
			</ul>
			<footer class="flex justify-end gap-3 pt-2">
				<button class="btn preset-outlined-surface-500" disabled={updateBusy} onclick={closeUpdate}>
					Cancel
				</button>
				<button class="btn preset-filled-primary-500" disabled={updateBusy} onclick={confirmUpdate}>
					{updateBusy ? 'Updating…' : 'Confirm update'}
				</button>
			</footer>
		{/if}
	</div>
</dialog>
