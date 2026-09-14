import os
import smtplib
from email.message import EmailMessage
from dotenv import load_dotenv

load_dotenv()

def _get_smtp_config() -> dict:
    host = os.getenv("SMTP_HOST", "").strip()
    port_raw = os.getenv("SMTP_PORT", "587").strip()
    username = os.getenv("SMTP_USERNAME", "").strip()
    password = os.getenv("SMTP_PASSWORD", "")
    from_email = (
        os.getenv("SMTP_FROM_EMAIL", "").strip()
        or username
    )

    if not host:
        raise RuntimeError("SMTP_HOST is not configured.")

    try:
        port = int(port_raw)
    except ValueError as exc:
        raise RuntimeError(
            "SMTP_PORT must be a valid integer."
        ) from exc

    if not username:
        raise RuntimeError(
            "SMTP_USERNAME is not configured."
        )

    if not password:
        raise RuntimeError(
            "SMTP_PASSWORD is not configured."
        )

    if not from_email:
        raise RuntimeError(
            "SMTP_FROM_EMAIL is not configured."
        )

    return {
        "host": host,
        "port": port,
        "username": username,
        "password": password,
        "from_email": from_email,
    }


def send_email_verification(
    recipient_email: str,
    recipient_name: str,
    verification_token: str,
) -> None:
    """
    Send an email-verification message.

    The raw verification token is only sent by email.
    The database stores only its hash.
    """

    config = _get_smtp_config()

    frontend_url = os.getenv(
        "FRONTEND_URL",
        "http://localhost:3000",
    ).rstrip("/")

    verification_url = (
        f"{frontend_url}/verify-email"
        f"?token={verification_token}"
        f"&email={recipient_email}"
    )

    display_name = recipient_name.strip() or "there"

    message = EmailMessage()

    message["Subject"] = (
        "Verify your email — Prescription Intelligence"
    )
    message["From"] = config["from_email"]
    message["To"] = recipient_email

    text_body = f"""Hello {display_name},

Welcome to Prescription Intelligence.

Please verify your email address to activate your account.

Verify your email:
{verification_url}

This verification link will expire in 30 minutes.

If you did not create this account, you can safely ignore this email.

Regards,
Prescription Intelligence
"""

    html_body = f"""\
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>Verify your email</title>
</head>
<body style="
    margin: 0;
    padding: 0;
    background: #F4F7F5;
    font-family: Arial, Helvetica, sans-serif;
">
    <div style="
        max-width: 620px;
        margin: 40px auto;
        background: #FFFFFF;
        border: 1px solid #DFE6E1;
        border-radius: 12px;
        overflow: hidden;
    ">
        <div style="
            padding: 28px 32px;
            border-bottom: 1px solid #DFE6E1;
        ">
            <div style="
                font-size: 13px;
                font-weight: 700;
                letter-spacing: 0.08em;
                color: #35664D;
                text-transform: uppercase;
            ">
                Prescription Intelligence
            </div>
        </div>

        <div style="padding: 32px;">
            <h1 style="
                margin: 0 0 16px;
                color: #17211D;
                font-size: 26px;
                line-height: 1.25;
            ">
                Verify your email
            </h1>

            <p style="
                color: #526158;
                font-size: 15px;
                line-height: 1.6;
            ">
                Hello {display_name},
            </p>

            <p style="
                color: #526158;
                font-size: 15px;
                line-height: 1.6;
            ">
                Welcome to Prescription Intelligence.
                Please verify your email address to activate
                your account.
            </p>

            <div style="margin: 28px 0;">
                <a
                    href="{verification_url}"
                    style="
                        display: inline-block;
                        padding: 13px 22px;
                        background: #35664D;
                        color: #FFFFFF;
                        text-decoration: none;
                        border-radius: 7px;
                        font-size: 14px;
                        font-weight: 700;
                    "
                >
                    Verify email address
                </a>
            </div>

            <p style="
                color: #7C8881;
                font-size: 13px;
                line-height: 1.6;
            ">
                This verification link expires in 30 minutes.
            </p>

            <p style="
                color: #7C8881;
                font-size: 13px;
                line-height: 1.6;
            ">
                If the button does not work, copy this link
                into your browser:
            </p>

            <p style="
                color: #526158;
                font-size: 12px;
                line-height: 1.6;
                word-break: break-all;
            ">
                {verification_url}
            </p>

            <p style="
                margin-top: 28px;
                color: #7C8881;
                font-size: 13px;
                line-height: 1.6;
            ">
                If you did not create this account, you can
                safely ignore this email.
            </p>
        </div>
    </div>
</body>
</html>
"""

    message.set_content(text_body)
    message.add_alternative(
        html_body,
        subtype="html",
    )

    with smtplib.SMTP(
        config["host"],
        config["port"],
        timeout=20,
    ) as server:
        server.ehlo()
        server.starttls()
        server.ehlo()
        server.login(
            config["username"],
            config["password"],
        )
        server.send_message(message)