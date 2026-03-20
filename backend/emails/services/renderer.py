from jinja2 import Template


def render_template(template_string: str, context: dict) -> str:
    """Render a Jinja2 template string with the given context."""
    template = Template(template_string)
    return template.render(**context)
