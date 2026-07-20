from jinja2 import Template


def build_context(company_name: str, email: str) -> dict:
    """Build the Jinja2 context for email templates.

    Provides:
      - company_name
      - email
      - definite_article_company_name: the company name prefixed with its correct
        French definite article (e.g. "la MSP du Marais", "le Pôle de santé",
        "l'Association ...").

    Raises webprospects.french.UnknownArticleError if the company's head noun has
    no known gender — callers must handle it (never send with a missing article).
    """
    from webprospects.french import article_or_raise

    return {
        "company_name": company_name,
        "email": email,
        "definite_article_company_name": article_or_raise(company_name),
    }


def render_template(template_string: str, context: dict) -> str:
    """Render a Jinja2 template string with the given context."""
    template = Template(template_string)
    return template.render(**context)
