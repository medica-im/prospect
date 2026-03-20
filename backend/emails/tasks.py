import logging

from celery import shared_task

from .models import EmailTemplate, SentEmail, CompanyType
from .services.mailgun import send_email
from .services.imap import save_to_sent_folder
from .services.renderer import render_template

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def send_prospect_email(
    self,
    template_id: int,
    company_name: str,
    company_email: str,
    company_type_id: int,
    twenty_crm_id: str,
) -> dict:
    """Send a single prospect email via Mailgun and save to IMAP Sent folder."""
    template = EmailTemplate.objects.get(id=template_id)
    company_type = CompanyType.objects.get(id=company_type_id)
    context = {"company_name": company_name, "email": company_email}

    subject = render_template(template.subject_template, context)
    html_body = render_template(template.html_body, context)

    sent_email = SentEmail.objects.create(
        template=template,
        company_name=company_name,
        company_email=company_email,
        company_type=company_type,
        twenty_crm_id=twenty_crm_id,
        success=False,
    )

    try:
        result = send_email(to=company_email, subject=subject, html_body=html_body)
        mailgun_message_id = result.get("id", "")

        sent_email.success = True
        sent_email.mailgun_message_id = mailgun_message_id
        sent_email.save(update_fields=["success", "mailgun_message_id"])

        try:
            save_to_sent_folder(to=company_email, subject=subject, html_body=html_body)
        except Exception as e:
            logger.warning(f"Failed to save email to IMAP Sent folder: {e}")

        return {"status": "sent", "sent_email_id": sent_email.id}

    except Exception as exc:
        sent_email.error_message = str(exc)
        sent_email.save(update_fields=["error_message"])
        logger.error(f"Failed to send email to {company_email}: {exc}")
        raise self.retry(exc=exc)
