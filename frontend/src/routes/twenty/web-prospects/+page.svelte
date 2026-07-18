<script lang="ts">
	import MspCard, { type MspRecord } from '$lib/webprospects/MspCard.svelte';
	import ReportTable, { type ReportRow } from '$lib/webprospects/ReportTable.svelte';

	type ScrapedRecord = {
		record: MspRecord;
		missing_fields: string[];
		existing_count: number;
		existing_ids: string[];
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

	// --- Direct run flow ---
	let runProgress = $state({ processed: 0, total: 0, created: 0, already_present: 0, skipped: 0, failed: 0 });
	let pollTimer: ReturnType<typeof setInterval> | null = null;

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
		if (pollTimer) clearInterval(pollTimer);
		pollTimer = null;
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
		phase = 'scraping';
		try {
			const res = await fetch('/twenty/web-prospects/api/scrape', {
				method: 'POST',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify({ url, scraper: suggestion })
			});
			const json = await res.json();
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
			const json = await res.json();
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
					error: json.error
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

	// --- Direct run (no confirmation) ---
	async function runAll() {
		phase = 'running';
		runProgress = { processed: 0, total: 0, created: 0, already_present: 0, skipped: 0, failed: 0 };
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
			const json = await res.json();
			if (!res.ok) {
				error = json.detail || 'Run failed';
				phase = 'idle';
				return;
			}
			pollTimer = setInterval(() => pollRun(json.task_id), 2000);
		} catch (e) {
			error = String(e);
			phase = 'idle';
		}
	}

	async function pollRun(taskId: string) {
		try {
			const res = await fetch(`/twenty/web-prospects/api/run-status?task_id=${encodeURIComponent(taskId)}`);
			const json = await res.json();
			if (json.state === 'PROGRESS') {
				runProgress = {
					processed: json.processed ?? 0,
					total: json.total ?? 0,
					created: json.created ?? 0,
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
	<aside class="alert preset-filled-error-500 mb-6">
		<p>{error}</p>
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
		<div class="mb-4 text-sm text-surface-500">
			{scraped.length} MSP found. Reviewing card {currentIndex + 1} of {scraped.length}.
		</div>
		{#if currentCard}
			<MspCard
				bind:record={scraped[currentIndex].record}
				missingFields={currentCard.missing_fields}
				existingCount={currentCard.existing_count}
				index={currentIndex}
				total={scraped.length}
				busy={cardBusy}
				onConfirm={confirmCurrent}
				onSkip={skipCurrent}
			/>
		{/if}
		{#if reportRows.length > 0}
			<div class="mt-6">
				<ReportTable rows={reportRows} title="Processed so far" />
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
				<span class="text-yellow-600">{runProgress.already_present} already present</span>
				<span class="text-red-600">{runProgress.failed} failed</span>
			</div>
		{:else}
			<p class="text-surface-500">Starting…</p>
		{/if}
	</div>
{/if}

<!-- Done -->
{#if phase === 'done'}
	<div class="space-y-6">
		<aside class="alert preset-filled-success-500">
			<p>Done. {reportRows.filter((r) => r.status === 'created').length} created.</p>
		</aside>
		<ReportTable rows={reportRows} title="Report" />
		<button class="btn preset-filled-primary-500" onclick={reset}>Process another page</button>
	</div>
{/if}
