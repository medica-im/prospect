"""Scraper for apmsl.fr MSP (maison de santé pluriprofessionnelle) listings.

Each organisation is rendered inside a ``<div class="modal-body">`` block like:

    <div class="modal-body">
        <img ... title="POLE DE SANTE DU MARAIS" ...>
        8 rue de la garde<br>85300 SALLERTAINE<br><br>
        <strong>Numéro Finess :</strong> 850026410<br>
        <strong>Date d'enregistrement Finess :</strong> 22/09/2016<br>
        <strong>Type de projet :</strong> Maison de Santé Pluriprofessionnelle (MSP) multi-sites<br>
        <strong>Coordinateur(s) :</strong>
        <ul><li>ROUSSEAU Stéphanie</li></ul>
        <strong>Team Leader(s) :</strong>
        <ul><li>ZINUTTI Marie</li></ul>
        <div class="entite-contact">
            <a href="mailto:poledesantedumarais@gmail.com">...</a>
            <a href="www.polesantemarais.fr">...</a>
            <a href="tel:0636863729">...</a>
        </div>
    </div>
"""
import re

from bs4 import BeautifulSoup, NavigableString, Tag


def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").replace("\xa0", " ")).strip()


def _person_from_line(line: str) -> dict:
    """apmsl lists people as 'LASTNAME Firstname' (last name uppercase first).

    Returns {'first_name': ..., 'last_name': ...}. Best-effort: the first
    UPPERCASE token(s) are the last name, the rest is the first name.
    """
    line = _clean(line)
    if not line:
        return {"first_name": "", "last_name": ""}
    tokens = line.split(" ")
    last_tokens = []
    first_tokens = []
    for tok in tokens:
        # A token is part of the surname while it is (mostly) uppercase and we
        # haven't started collecting the first name yet.
        letters = [c for c in tok if c.isalpha()]
        is_upper = bool(letters) and all(c.isupper() for c in letters)
        if is_upper and not first_tokens:
            last_tokens.append(tok)
        else:
            first_tokens.append(tok)
    # Fallbacks if the heuristic collected nothing on one side.
    if not first_tokens:
        first_tokens, last_tokens = last_tokens, []
    return {
        "first_name": _clean(" ".join(first_tokens)).title() if first_tokens else "",
        "last_name": _clean(" ".join(last_tokens)).title() if last_tokens else "",
    }


def _people_after_label(label_strong: Tag) -> list[dict]:
    """Collect <li> items from the <ul> that follows a <strong> label."""
    people = []
    for sib in label_strong.next_siblings:
        if isinstance(sib, Tag):
            if sib.name == "ul":
                seen = set()
                for li in sib.find_all("li"):
                    person = _person_from_line(li.get_text())
                    if not (person["first_name"] or person["last_name"]):
                        continue
                    key = (person["first_name"], person["last_name"])
                    if key in seen:
                        continue
                    seen.add(key)
                    people.append(person)
                break
            if sib.name == "strong":
                # Reached the next label without hitting a <ul>.
                break
    return people


def _value_after_label(label_strong: Tag) -> str:
    """Text value immediately following a <strong> label, up to the next <br>."""
    parts = []
    for sib in label_strong.next_siblings:
        if isinstance(sib, Tag):
            if sib.name in ("br", "strong", "ul", "div"):
                break
        parts.append(sib.get_text() if isinstance(sib, Tag) else str(sib))
    return _clean("".join(parts))


def _name_for_block(block: Tag, img: Tag | None) -> str:
    """Company name: prefer the enclosing modal's title, fall back to img title/alt.

    Blocks without a logo <img> carry the name only in the modal header
    (``.modal-title``), so walk up to find it.
    """
    node = block
    for _ in range(6):
        node = node.parent
        if not isinstance(node, Tag):
            break
        if "modal" in (node.get("class") or []):
            title_el = node.find(class_="modal-title")
            if title_el:
                title = _clean(title_el.get_text())
                if title:
                    return title
            break
    if img is not None:
        return _clean(img.get("title") or img.get("alt") or "")
    return ""


def _find_label(block: Tag, needle: str) -> Tag | None:
    needle = needle.lower()
    for strong in block.find_all("strong"):
        if needle in _clean(strong.get_text()).lower():
            return strong
    return None


def _address_lines(block: Tag, img: Tag | None) -> tuple[str, str, str]:
    """Return (address_line1, postcode, city).

    The address sits as bare text nodes between the <img> and the first
    <strong>, separated by <br>. Typical shape:
        'ADDRESS LINE 1' <br> '85300 SALLERTAINE' <br><br> <strong>...
    """
    start = img if img is not None else block
    collected = []
    node = start
    # Walk forward through siblings until the first <strong> (the Finess block).
    iterator = start.next_siblings if img is not None else block.children
    for sib in iterator:
        if isinstance(sib, Tag):
            if sib.name == "strong":
                break
            if sib.name == "br":
                collected.append("\n")
                continue
            if sib.name == "img":
                continue
            if sib.name == "div":
                break
            collected.append(sib.get_text())
        else:
            collected.append(str(sib))
    raw = "".join(collected)
    lines = [_clean(l) for l in raw.split("\n") if _clean(l)]

    address_line1 = lines[0] if lines else ""
    postcode = ""
    city = ""
    if len(lines) > 1:
        # Second line looks like '85300 SALLERTAINE'
        m = re.match(r"^\s*(\d{4,5})\s+(.*)$", lines[1])
        if m:
            postcode = m.group(1)
            city = _clean(m.group(2))
        else:
            city = lines[1]
    return address_line1, postcode, city


def _text_without_icons(anchor: Tag) -> str:
    """Text content of an <a>, excluding material-icons <span> glyph names."""
    parts = []
    for child in anchor.descendants:
        if isinstance(child, NavigableString):
            parent = child.parent
            if isinstance(parent, Tag) and "material-icons" in (parent.get("class") or []):
                continue
            parts.append(str(child))
    return "".join(parts)


def _contact(block: Tag) -> dict:
    """Extract email / website / phone from the entite-contact div."""
    email = ""
    website = ""
    phone = ""
    contact_div = block.find("div", class_="entite-contact")
    if not contact_div:
        return {"email": email, "website": website, "phone": phone}
    for a in contact_div.find_all("a", href=True):
        href = a["href"].strip()
        if href.startswith("mailto:"):
            email = href[len("mailto:"):].strip()
        elif href.startswith("tel:"):
            # The link text includes a material-icons span (e.g. "phone_iphone");
            # drop it and keep only the human-readable number, else the tel: value.
            text = _clean(_text_without_icons(a))
            phone = text or href[len("tel:"):].strip()
        else:
            website = href
    return {"email": email, "website": website, "phone": phone}


def _normalize_website(url: str) -> str:
    url = _clean(url)
    if not url:
        return ""
    if not re.match(r"^https?://", url, re.I):
        url = "https://" + url.lstrip("/")
    return url


def parse_apmsl(html: str) -> list[dict]:
    """Parse an apmsl.fr page and return a list of MSP records."""
    soup = BeautifulSoup(html, "html.parser")
    records = []

    for block in soup.find_all("div", class_="modal-body"):
        img = block.find("img")
        name = _name_for_block(block, img)

        address_line1, postcode, city = _address_lines(block, img)

        finess_label = _find_label(block, "Numéro Finess")
        finess = _value_after_label(finess_label) if finess_label else ""

        date_label = _find_label(block, "Date d'enregistrement")
        finess_date = _value_after_label(date_label) if date_label else ""

        project_label = _find_label(block, "Type de projet")
        project_type = _value_after_label(project_label) if project_label else ""

        coord_label = _find_label(block, "Coordinateur")
        coordinators = _people_after_label(coord_label) if coord_label else []

        lead_label = _find_label(block, "Team Leader")
        team_leaders = _people_after_label(lead_label) if lead_label else []

        contact = _contact(block)

        records.append({
            "name": name,
            "address_line1": address_line1,
            "postcode": postcode,
            "city": city,
            "finess_number": finess,
            "finess_date": finess_date,
            "project_type": project_type,
            "coordinators": coordinators,
            "team_leaders": team_leaders,
            "email": contact["email"],
            "phone": contact["phone"],
            "website": _normalize_website(contact["website"]),
        })

    return records
