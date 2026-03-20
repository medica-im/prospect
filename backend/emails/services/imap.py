from email.message import EmailMessage
from email.utils import formatdate

from imap_tools import MailBox, MailMessageFlags, MailMessage
from django.conf import settings


def save_to_sent_folder(to: str, subject: str, html_body: str) -> None:
    """Save a sent email to the IMAP Sent folder."""
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = settings.IMAP_EMAIL
    msg["To"] = to
    msg["Date"] = formatdate(localtime=True)
    msg.set_content(html_body, subtype="html")

    email_bytes = msg.as_bytes()
    mail_msg = MailMessage.from_bytes(email_bytes)

    with MailBox(settings.IMAP_SERVER).login(
        settings.IMAP_EMAIL, settings.IMAP_PASSWORD
    ) as mailbox:
        mailbox.append(mail_msg, folder="Sent", flag_set=[MailMessageFlags.SEEN])


def fetch_email_from_sent(subject: str, sent_date: str) -> str | None:
    """
    Fetch a specific email from IMAP Sent folder by subject and date.
    sent_date should be in DD-Mon-YYYY format (e.g. 20-Mar-2026).
    Returns the HTML body or None if not found.
    """
    with MailBox(settings.IMAP_SERVER).login(
        settings.IMAP_EMAIL, settings.IMAP_PASSWORD
    ) as mailbox:
        mailbox.folder.set("Sent")
        criteria = f'(SUBJECT "{subject}" ON {sent_date})'
        for msg in mailbox.fetch(criteria, charset="utf-8", reverse=True, limit=1):
            return msg.html or msg.text
    return None
