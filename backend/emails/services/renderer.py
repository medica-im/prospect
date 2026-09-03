from jinja2 import Template


def build_context(company_name: str, email: str, unsubscribe_url: str = "") -> dict:
    """Build the Jinja2 context for email templates.

    Provides:
      - company_name
      - email
      - definite_article_company_name: the company name prefixed with its correct
        French definite article (e.g. "la MSP du Marais", "le Pôle de santé",
        "l'Association ...").
      - unsubscribe_url: absolute opt-out link for this recipient. Empty when
        rendering outside a real send (previews), so templates referencing it
        never raise.

    Raises webprospects.french.UnknownArticleError if the company's head noun has
    no known gender — callers must handle it (never send with a missing article).
    """
    from webprospects.french import article_or_raise

    return {
        "company_name": company_name,
        "email": email,
        "definite_article_company_name": article_or_raise(company_name),
        "unsubscribe_url": unsubscribe_url,
    }


def render_template(template_string: str, context: dict) -> str:
    """Render a Jinja2 template string with the given context."""
    template = Template(template_string)
    return template.render(**context)


UNSUBSCRIBE_FOOTER = (
    '<div style="margin:24px 0 0;padding:16px 0 0;border-top:1px solid #e0e0e0;'
    'font-family:Helvetica,Arial,sans-serif;font-size:12px;color:#888888;'
    'text-align:center;">'
    'Vous ne souhaitez plus recevoir nos emails ? '
    '<a href="{url}" style="color:#888888;">Se désabonner</a>.'
    "</div>"
)


def ensure_unsubscribe_link(html_body: str, unsubscribe_url: str) -> str:
    """Guarantee the rendered email carries its opt-out link.

    Templates are authored by hand in the admin, so one may simply forget
    {{ unsubscribe_url }}. Rather than send a link-less prospecting email, append
    a plain footer before </body> (or at the end when there is no body tag).
    """
    if not unsubscribe_url or unsubscribe_url in html_body:
        return html_body

    footer = UNSUBSCRIBE_FOOTER.format(url=unsubscribe_url)
    lower = html_body.lower()
    index = lower.rfind("</body>")
    if index == -1:
        return html_body + footer
    return html_body[:index] + footer + html_body[index:]
