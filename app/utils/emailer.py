import smtplib
from email.message import EmailMessage
from typing import Optional, Tuple

from flask import current_app


def _as_bool(value, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    s = str(value).strip().lower()
    if s in {"1", "true", "yes", "y", "on"}:
        return True
    if s in {"0", "false", "no", "n", "off"}:
        return False
    return default


def send_email(
    to_email: str,
    subject: str,
    body: str,
    *,
    from_email: Optional[str] = None,
) -> Tuple[bool, Optional[str]]:
    """Send a plain-text email.

    Uses SMTP settings from app config:
    - SMTP_HOST, SMTP_PORT
    - SMTP_USERNAME, SMTP_PASSWORD
    - SMTP_USE_TLS (STARTTLS), SMTP_USE_SSL
    - SMTP_FROM (optional)

    Returns: (sent_ok, error_message)
    """
    host = (current_app.config.get("SMTP_HOST") or "").strip()
    port = int(current_app.config.get("SMTP_PORT") or 0)
    username = current_app.config.get("SMTP_USERNAME")
    password = current_app.config.get("SMTP_PASSWORD")

    use_tls = _as_bool(current_app.config.get("SMTP_USE_TLS"), default=False)
    use_ssl = _as_bool(current_app.config.get("SMTP_USE_SSL"), default=False)

    if not host or not port:
        return False, "SMTP not configured (SMTP_HOST/SMTP_PORT)"

    sender = (from_email or current_app.config.get("SMTP_FROM") or username or "").strip()
    if not sender:
        return False, "SMTP sender not configured (SMTP_FROM or SMTP_USERNAME)"

    msg = EmailMessage()
    msg["From"] = sender
    msg["To"] = to_email
    msg["Subject"] = subject
    msg.set_content(body)

    try:
        if use_ssl:
            server: smtplib.SMTP = smtplib.SMTP_SSL(host, port, timeout=20)
        else:
            server = smtplib.SMTP(host, port, timeout=20)

        try:
            server.ehlo()
            if use_tls and not use_ssl:
                server.starttls()
                server.ehlo()
            if username and password:
                server.login(str(username), str(password))
            server.send_message(msg)
        finally:
            try:
                server.quit()
            except Exception:
                pass

        return True, None
    except Exception as e:
        current_app.logger.exception("SMTP send failed")
        return False, str(e)


def send_student_credentials_email(
    *,
    to_email: str,
    student_name: str,
    password: str,
    login_url: str,
) -> Tuple[bool, Optional[str]]:
    subject = "Your EduSaint Login Credentials"
    body = (
        f"Hi {student_name or 'Student'},\n\n"
        "Your account has been created.\n\n"
        f"Email: {to_email}\n"
        f"Password: {password}\n\n"
        f"Login here: {login_url}\n\n"
        "For security, please change your password after first login.\n\n"
        "Regards,\n"
        "EduSaint\n"
    )
    return send_email(to_email=to_email, subject=subject, body=body)


def send_student_new_password_email(
    *,
    to_email: str,
    student_name: str,
    password: str,
    login_url: str,
) -> Tuple[bool, Optional[str]]:
    subject = "Your EduSaint Password Has Been Updated"
    body = (
        f"Hi {student_name or 'Student'},\n\n"
        "Your password has been updated by an admin.\n\n"
        f"Email: {to_email}\n"
        f"New Password: {password}\n\n"
        f"Login here: {login_url}\n\n"
        "For security, please change your password after login.\n\n"
        "Regards,\n"
        "EduSaint\n"
    )
    return send_email(to_email=to_email, subject=subject, body=body)


def send_staff_credentials_email(
    *,
    to_email: str,
    staff_name: str,
    password: str,
    login_url: str,
) -> Tuple[bool, Optional[str]]:
    subject = "Your EduSaint Staff Login Credentials"
    body = (
        f"Hi {staff_name or 'Staff'},\n\n"
        "Your staff account has been created.\n\n"
        f"Email: {to_email}\n"
        f"Password: {password}\n\n"
        f"Login here: {login_url}\n\n"
        "For security, please change your password after first login.\n\n"
        "Regards,\n"
        "EduSaint Team\n"
    )
    return send_email(to_email=to_email, subject=subject, body=body)
