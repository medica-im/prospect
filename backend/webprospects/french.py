"""French definite-article selection for organisation names.

The correct article (la / le / l') depends on the grammatical gender of the
name's *head noun* (its first significant word) and whether that word begins
with a vowel or mute h (elision → l').

Gender is not reliably derivable from spelling, so it comes from a lookup table
(HeadNounGender). Unknown head nouns return no article and are flagged, so we
never emit wrong French automatically.
"""
import re
import unicodedata

# Leading definite articles to skip when finding the head noun.
_LEADING_ARTICLES = {"la", "le", "les", "l"}

# Vowels for elision (accented forms included). Mute-h words are handled by the
# explicit set below; aspirated-h words (le héros) are NOT elided.
_VOWELS = set("aàâäeéèêëiîïoôöuùûüy")

# Words starting with a mute (silent) h that DO elide: l'hôpital, l'hôtel…
# Extend as needed; unknown h-words default to non-elision (safer for CRM text).
_MUTE_H_WORDS = {"hôpital", "hopital", "hôtel", "hotel", "hôtel-dieu"}


def head_noun(name: str) -> str:
    """Return the lowercased head noun of a company name (first significant word,
    skipping any leading definite article). Empty string if none found."""
    tokens = re.findall(r"[0-9A-Za-zÀ-ÿ'’]+", name or "")
    for tok in tokens:
        low = tok.lower()
        # An elided article attaches to the next word: "l'entreprise" → "entreprise".
        if low.startswith("l'") or low.startswith("l’"):
            rest = low[2:]
            if rest:
                return rest
        stripped = low.strip("'’")
        if stripped in _LEADING_ARTICLES:
            continue
        return stripped
    return ""


def _elides(word: str) -> bool:
    """True if the head noun triggers elision (l')."""
    if not word:
        return False
    if word in _MUTE_H_WORDS:
        return True
    first = word[0]
    return first in _VOWELS


def article_for_gender(head: str, gender: str) -> str | None:
    """Given a head noun and its gender ('f'/'m'), return 'la'/'le'/"l'".

    Returns None if the gender is unknown, so the caller can flag for review.
    """
    if gender not in ("f", "m"):
        return None
    if _elides(head):
        return "l'"
    return "la" if gender == "f" else "le"


def resolve_article(name: str, gender_lookup) -> dict:
    """Resolve the definite article for a company name.

    ``gender_lookup`` maps a head noun (lowercased) → gender ('f'/'m'/'unknown'
    or None if absent). Kept as a callable/dict so this stays DB-agnostic and
    unit-testable.

    Returns:
        {
          "head_noun": str,
          "article": str | None,      # 'la' | 'le' | "l'" | None
          "with_article": str,        # "la MSP ..."  (name unchanged if no article)
          "needs_review": bool,       # True when the head noun is unknown/ungendered
        }
    """
    head = head_noun(name)
    gender = None
    if head:
        gender = gender_lookup.get(head) if isinstance(gender_lookup, dict) else gender_lookup(head)

    article = article_for_gender(head, gender) if gender else None
    if article == "l'":
        with_article = f"l'{name}"
    elif article:
        with_article = f"{article} {name}"
    else:
        with_article = name

    return {
        "head_noun": head,
        "article": article,
        "with_article": with_article,
        "needs_review": article is None,
    }


def resolve_article_db(name: str) -> dict:
    """resolve_article() using the HeadNounGender DB table as the gender source."""
    from .models import HeadNounGender

    head = head_noun(name)
    gender = None
    if head:
        row = HeadNounGender.objects.filter(head_noun=head).first()
        if row:
            gender = row.gender
    return resolve_article(name, {head: gender} if head else {})


class UnknownArticleError(ValueError):
    """Raised when a company's head noun has no known French gender, so the
    definite article cannot be determined. Carries context for the operator."""

    def __init__(self, company_name: str, head: str, admin_url: str):
        self.company_name = company_name
        self.head_noun = head
        self.admin_url = admin_url
        if head:
            msg = (
                f"No French definite article for company \"{company_name}\": the head "
                f"noun \"{head}\" has no known gender. Set its gender (f/m) here: {admin_url}"
            )
        else:
            msg = (
                f"No French definite article for company \"{company_name}\": could not "
                f"extract a head noun from the name. Review it here: {admin_url}"
            )
        super().__init__(msg)


def _admin_url_for_head(head: str) -> str:
    """Absolute Django-admin URL to fix a head noun's gender.

    Links to the existing row's change page if present, else the pre-filled add
    form so it can be created in one click.
    """
    from django.conf import settings

    from .models import HeadNounGender

    base = settings.ADMIN_BASE_URL.rstrip("/")
    if head:
        row = HeadNounGender.objects.filter(head_noun=head).first()
        if row:
            return f"{base}/admin/webprospects/headnoungender/{row.pk}/change/"
        return f"{base}/admin/webprospects/headnoungender/add/?head_noun={head}"
    return f"{base}/admin/webprospects/headnoungender/"


def article_or_raise(name: str) -> str:
    """Return the company name prefixed with its correct French definite article.

    Raises UnknownArticleError if the head noun's gender is unknown, rather than
    silently emitting the bare name.
    """
    resolved = resolve_article_db(name)
    if resolved["needs_review"]:
        raise UnknownArticleError(name, resolved["head_noun"], _admin_url_for_head(resolved["head_noun"]))
    return resolved["with_article"]
