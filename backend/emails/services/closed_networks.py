"""Addresses prospect never mails because no outside sender can reach them.

MSSanté is the secure messaging network of French healthcare professionals: only
senders inside it (or affiliated with it) can deliver to a mailbox there. Mailgun
is outside, so every send is refused ("530 5.7.0 Must issue a STARTTLS command
first"). The addresses are valid and stay in Twenty; they are just not offered
for prospecting, and they are not a problem to fix either.

The same rule lives in frontend/src/lib/emails/selection.ts (isClosedNetwork).
"""

from .unsubscribe import normalize

CLOSED_NETWORK_DOMAINS = ("mssante.fr",)


def is_closed_network(email: str) -> bool:
    """True for an address on a closed-network domain or any subdomain of it
    (aura.mssante.fr, paca.mssante.fr, ...)."""
    _local, at, domain = normalize(email).rpartition("@")
    return bool(at) and any(domain == d or domain.endswith(f".{d}") for d in CLOSED_NETWORK_DOMAINS)
