from .apmsl import parse_apmsl

# Registry of available scrapers: key -> parse function taking html -> list[dict].
SCRAPERS = {
    "apmsl": parse_apmsl,
}


def suggest_scraper(url: str) -> str | None:
    """Return the scraper key suggested for a given URL, or None."""
    host = url.lower().replace("https://", "").replace("http://", "")
    if host.startswith("apmsl.fr") or host.startswith("www.apmsl.fr"):
        return "apmsl"
    return None
