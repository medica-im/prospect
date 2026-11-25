"""Addresses that are in Twenty right now and whose latest send did not get through.

The history report in delivery.py (problem_addresses) is a log of what prospect
sent: since then many of its addresses were fixed or removed in Twenty. This
joins that history to what Twenty holds today, so it only lists addresses that
are still offered for prospecting but may no longer work.

Join on the address, never on SentEmail.twenty_crm_id: that id is sometimes a
company's and sometimes a person's.
"""

from datetime import datetime, timezone

from django.conf import settings
from django.core.cache import cache

from ..models import SentEmail
from .closed_networks import is_closed_network
from .delivery import address_histories, is_dead, is_problem_attempt, listed_reasons, problem_run_start
from .twenty_crm import fetch_companies, fetch_people
from .unsubscribe import normalize

SNAPSHOT_CACHE_KEY = "emails:twenty_address_snapshot"
SNAPSHOT_TTL_SECONDS = 600

WHERE_PRIMARY = "person_primary"
WHERE_ADDITIONAL = "person_additional"
WHERE_COMPANY = "company"

SEVERITY_DEAD = "dead"
SEVERITY_TROUBLESOME = "troublesome"
SEVERITY_PENDING = "pending"  # still being retried by Mailgun: "en attente"
_SEVERITY_RANK = {SEVERITY_DEAD: 0, SEVERITY_TROUBLESOME: 1, SEVERITY_PENDING: 2}

# What to do about an address, the short answer the page and the API give.
ACTION_REMOVE = "remove"  # permanently dead: delete the address from Twenty
ACTION_REVIEW = "review"  # unclear or possibly fine: look by hand
ACTION_RETRY = "retry"  # temporary: keep it and mail again later
ACTION_FIX = "fix"  # not the address's fault: fix it on our side
ACTIONS = (ACTION_REMOVE, ACTION_REVIEW, ACTION_RETRY, ACTION_FIX)

# Status of a send Mailgun refused to accept (SentEmail.success is False).
STATUS_SEND_FAILED = "send_failed"

UNKNOWN_SUPPRESSION = "unknown (Mailgun suppression)"


def advise(status: str, bounce_class: str, detail: str) -> tuple[str, str]:
    """(action, reason) for an address, from how its latest send failed.

    Only a failure that cannot heal says "remove": the domain does not exist, or
    the server says the mailbox does not exist or is closed. Everything else is
    kept: a full mailbox or an overloaded server passes, a policy block or an
    unreachable server says nothing about the address, and a refused send is
    our own template error.
    """
    text = " ".join((detail or "").lower().split())
    if status == STATUS_SEND_FAILED:
        return ACTION_FIX, "our_error"
    if status == SentEmail.DELIVERY_DEFERRED:
        return ACTION_RETRY, "retrying"
    if status == SentEmail.DELIVERY_COMPLAINED or text.startswith("spam complaint"):
        return ACTION_REVIEW, "spam_complaint"
    if bounce_class == SentEmail.BOUNCE_DOMAIN_MISSING:
        return ACTION_REMOVE, "domain_gone"
    if bounce_class == SentEmail.BOUNCE_MAILBOX_MISSING:
        closed = "5.7.13" in text or "disabled recipient" in text or "inactivity" in text
        return ACTION_REMOVE, "account_closed" if closed else "mailbox_unknown"
    if bounce_class == SentEmail.BOUNCE_MAILBOX_FULL:
        return ACTION_RETRY, "mailbox_full"
    if bounce_class == SentEmail.BOUNCE_BLOCKED:
        return ACTION_REVIEW, "policy_block"
    if "unable to connect to mx" in text:
        return ACTION_REVIEW, "server_unreachable"
    if status == SentEmail.DELIVERY_SUPPRESSED and not bounce_class:
        return ACTION_REVIEW, "suppressed_unknown"
    return ACTION_REVIEW, "other"


# --- Twenty snapshot ---------------------------------------------------------

def build_twenty_addresses() -> list[dict]:
    """Every address on a Twenty person (primary and additional) or company.

    An address held by several records appears once per record, so each place to
    fix it is listed. A person's address repeated in their own additionalEmails
    counts once, as the primary.
    """
    companies = {company["id"]: company for company in fetch_companies()}
    entries: list[dict] = []

    def add(address, where, person, company_id, company_name, company_type):
        address = normalize(address)
        if not address:
            return
        entries.append({
            "address": address,
            "where": where,
            "person_id": person["id"] if person else "",
            "person_name": person["name"] if person else "",
            "job_title": person["job_title"] if person else "",
            "company_id": company_id,
            "company_name": company_name,
            "company_type": company_type or "",
        })

    for person in fetch_people():
        company = companies.get(person["company_id"]) or {}
        owner = (
            person["company_id"],
            company.get("name") or person["company_name"],
            company.get("company_type") or person["company_type"],
        )
        seen = set()
        for address, where in [
            (person["primary_email"], WHERE_PRIMARY),
            *((extra, WHERE_ADDITIONAL) for extra in person["additional_emails"]),
        ]:
            if normalize(address) not in seen:
                seen.add(normalize(address))
                add(address, where, person, *owner)

    for company in companies.values():
        # The company address field is deprecated in Twenty (off on dev) but can
        # still be returned, and some production companies still hold one.
        for address in company["emails"]:
            add(address, WHERE_COMPANY, None, company["id"], company["name"], company["company_type"])

    return entries


def twenty_snapshot(refresh: bool = False) -> dict:
    """{"snapshot_at": datetime, "addresses": [...]}, cached for ten minutes.

    `refresh` bypasses the cache and replaces it. Raises httpx.HTTPError when
    Twenty cannot be reached.
    """
    if not refresh:
        cached = cache.get(SNAPSHOT_CACHE_KEY)
        if cached:
            return cached
    snapshot = {
        "snapshot_at": datetime.now(tz=timezone.utc),
        "addresses": build_twenty_addresses(),
    }
    cache.set(SNAPSHOT_CACHE_KEY, snapshot, timeout=SNAPSHOT_TTL_SECONDS)
    return snapshot


# --- Latest-attempt rule -----------------------------------------------------

def _twenty_url(entry: dict) -> str:
    base = (settings.TWENTY_API_URL or "").rstrip("/")
    if entry["person_id"]:
        return f"{base}/object/person/{entry['person_id']}"
    return f"{base}/object/company/{entry['company_id']}"


def judge(history: list[SentEmail], listed: tuple[str, str] | None = None) -> dict | None:
    """What the latest send to an address says, or None when it is fine.

    Only the latest attempt counts: bounced then delivered is fine, delivered
    then bounced is a problem. A send with no news yet counts as fine. `listed` is
    Mailgun's own record of the address (delivery.listed_reasons), used to explain
    a suppression when none of our sends bounced.
    """
    last = history[-1]
    if not last.success:
        return {
            "status": STATUS_SEND_FAILED, "severity": SEVERITY_TROUBLESOME,
            "bounce_class": "", "smtp_detail": last.error_message, "last": last,
        }
    if last.delivery_status == SentEmail.DELIVERY_DEFERRED:
        return {
            "status": last.delivery_status, "severity": SEVERITY_PENDING,
            "bounce_class": "", "smtp_detail": last.delivery_detail, "last": last,
        }
    if not is_problem_attempt(last):
        return None

    bounce_class, detail = last.bounce_class, last.delivery_detail
    if last.delivery_status == SentEmail.DELIVERY_SUPPRESSED:
        # Mailgun refuses every email after the first bounce, so the refusal
        # explains nothing: show the bounce that put the address on the list, from
        # our own history, else from Mailgun's list.
        original = next(
            (row for row in reversed(history)
             if row.success and row.delivery_status == SentEmail.DELIVERY_BOUNCED),
            None,
        )
        if original:
            bounce_class, detail = original.bounce_class, original.delivery_detail
        else:
            bounce_class, detail = listed or ("", UNKNOWN_SUPPRESSION)
    severity = (
        SEVERITY_DEAD if is_dead(last.delivery_status, last.bounce_class) else SEVERITY_TROUBLESOME
    )
    return {
        "status": last.delivery_status, "severity": severity,
        "bounce_class": bounce_class, "smtp_detail": detail, "last": last,
    }


def current_problem_addresses(
    severity: str = "dead", refresh: bool = False, action: str | None = None,
) -> dict:
    """{"snapshot_at", "count", "rows"} for addresses in Twenty whose latest send failed.

    severity "dead" keeps the ones to fix in the CRM (see is_dead); "all" adds the
    troublesome ones (full mailbox, policy block, refused send) and the ones
    Mailgun is still retrying. `action` (see advise) keeps only the rows with that
    advice and takes precedence over severity: an address to remove can be one the
    severity filter calls troublesome.
    """
    if action:
        severity = "all"
    snapshot = twenty_snapshot(refresh=refresh)
    # A closed-network address (MSSanté) always fails for us and is not a CRM error.
    entries = [e for e in snapshot["addresses"] if not is_closed_network(e["address"])]
    histories = address_histories({entry["address"] for entry in entries})
    listed = listed_reasons({
        address for address, history in histories.items()
        if history[-1].success and history[-1].delivery_status == SentEmail.DELIVERY_SUPPRESSED
    })

    rows = []
    for entry in entries:
        history = histories.get(entry["address"])
        verdict = judge(history, listed.get(entry["address"])) if history else None
        if verdict is None:
            continue
        if severity == "dead" and verdict["severity"] != SEVERITY_DEAD:
            continue
        last = verdict.pop("last")
        verdict["action"], verdict["reason"] = advise(
            verdict["status"], verdict["bounce_class"], verdict["smtp_detail"],
        )
        if action and verdict["action"] != action:
            continue
        rows.append({
            **entry,
            **verdict,
            "attempts": len(history),
            "first_sent_at": history[0].sent_at,
            "first_problem_at": problem_run_start(history, last),
            "last_attempt_at": last.sent_at,
            "twenty_url": _twenty_url(entry),
        })

    rows.sort(key=lambda r: (
        _SEVERITY_RANK[r["severity"]], -r["last_attempt_at"].timestamp(), r["address"],
    ))
    return {"snapshot_at": snapshot["snapshot_at"], "count": len(rows), "rows": rows}
