from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy.orm import Session

from backend.auth import get_current_user, require_pharmacy_staff
from backend.database import get_db
from backend.models import CustomerDB, OrganizationDB, UserDB
from backend.security import (
    generate_email_verification_token,
    hash_email_verification_token,
    hash_password,
)
from backend.services.customer_service import get_customer_by_user
from backend.services.email_service import send_email_verification


router = APIRouter(
    prefix="/users",
    tags=["Users"],
)

@router.get(
    "/search",
)
def search_customers(
    q: str = Query(min_length=1, max_length=100),
    current_user: UserDB = Depends(require_pharmacy_staff),
    db: Session = Depends(get_db),
):
    organization = current_user.organization

    if organization is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Pharmacy organization is required",
        )

    search_term = q.strip()

    if not search_term:
        return []

    pattern = f"%{search_term}%"

    customers = (
        db.query(CustomerDB)
        .filter(
            CustomerDB.organization_id == organization.id,
            CustomerDB.is_active.is_(True),
            (
                CustomerDB.name.ilike(pattern)
                | CustomerDB.customer_code.ilike(pattern)
                | CustomerDB.phone.ilike(pattern)
                | CustomerDB.email.ilike(pattern)
            ),
        )
        .order_by(CustomerDB.name.asc())
        .limit(20)
        .all()
    )

    return customers

@router.get("/me")
def get_my_profile(
    current_user: UserDB = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Return the authenticated user's profile.
    """

    organization = current_user.organization

    customer = None

    if current_user.role == "customer":
        customer = get_customer_by_user(
            current_user.id,
            db,
        )

    return {
        "id": str(current_user.id),
        "name": current_user.name,
        "email": current_user.email,
        "role": current_user.role,
        "is_active": current_user.is_active,
        "organization": (
            {
                "id": str(organization.id),
                "name": organization.name,
                "slug": organization.slug,
            }
            if organization
            else None
        ),
        "customer": (
            {
                "id": str(customer.id),
                "customer_code": customer.customer_code,
                "name": customer.name,
                "phone": customer.phone,
                "email": customer.email,
            }
            if customer
            else None
        ),
        "created_at": current_user.created_at,
        "last_login_at": current_user.last_login_at,
    }


# =========================================================
# ORGANIZATION PROFILE
# =========================================================


class OrganizationUpdateRequest(BaseModel):
    """Fields that a pharmacist may update for their own organization."""

    name: Optional[str] = Field(
        default=None,
        min_length=2,
        max_length=200,
    )
    phone: Optional[str] = Field(
        default=None,
        max_length=30,
    )
    email: Optional[EmailStr] = None
    address: Optional[str] = Field(
        default=None,
        max_length=500,
    )


@router.get("/organization")
def get_my_organization(
    current_user: UserDB = Depends(require_pharmacy_staff),
    db: Session = Depends(get_db),
):
    """
    Return the authenticated pharmacist's organization profile.
    """
    if not current_user.organization_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Pharmacist is not associated with an organization",
        )

    organization = (
        db.query(OrganizationDB)
        .filter(OrganizationDB.id == current_user.organization_id)
        .first()
    )

    if not organization:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Organization not found",
        )

    return {
        "id": str(organization.id),
        "name": organization.name,
        "slug": organization.slug,
        "phone": organization.phone,
        "email": organization.email,
        "address": organization.address,
        "is_active": organization.is_active,
        "created_at": organization.created_at,
    }


@router.patch("/organization")
def update_my_organization(
    request: OrganizationUpdateRequest,
    current_user: UserDB = Depends(require_pharmacy_staff),
    db: Session = Depends(get_db),
):
    """
    Update the authenticated pharmacist's organization profile.

    Only pharmacists belonging to the organization may update it.
    Tenant isolation is enforced: a pharmacist can only modify
    their own organization.
    """
    if not current_user.organization_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Pharmacist is not associated with an organization",
        )

    organization = (
        db.query(OrganizationDB)
        .filter(OrganizationDB.id == current_user.organization_id)
        .first()
    )

    if not organization:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Organization not found",
        )

    # Apply only the fields that were explicitly provided.
    if request.name is not None:
        organization.name = request.name.strip()

    if request.phone is not None:
        organization.phone = request.phone.strip() or None

    if request.email is not None:
        organization.email = str(request.email).lower().strip()

    if request.address is not None:
        organization.address = request.address.strip() or None

    db.commit()
    db.refresh(organization)

    return {
        "id": str(organization.id),
        "name": organization.name,
        "slug": organization.slug,
        "phone": organization.phone,
        "email": organization.email,
        "address": organization.address,
        "is_active": organization.is_active,
        "created_at": organization.created_at,
    }


# =========================================================
# ORGANIZATION MEMBERS
# =========================================================


@router.get("/organization/members")
def get_organization_members(
    current_user: UserDB = Depends(require_pharmacy_staff),
    db: Session = Depends(get_db),
):
    """
    Return the staff members of the current user's organization.

    Only pharmacists are returned — customers are excluded.
    No passwords, tokens, or sensitive authentication fields are returned.
    Organization ID is always taken from the authenticated user context —
    never from client input.
    """
    if not current_user.organization_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Pharmacist is not associated with an organization",
        )

    members = (
        db.query(UserDB)
        .filter(
            UserDB.organization_id == current_user.organization_id,
            UserDB.role == "pharmacist",
        )
        .order_by(UserDB.created_at.asc())
        .all()
    )

    return [
        {
            "id": str(member.id),
            "name": member.name,
            "email": member.email,
            "role": member.role,
            "is_active": member.is_active,
            "email_verified": member.email_verified,
            "created_at": (
                member.created_at.isoformat()
                if member.created_at
                else None
            ),
        }
        for member in members
    ]


# =========================================================
# PHARMACIST INVITATION
# =========================================================

INVITE_TOKEN_EXPIRE_MINUTES = 72 * 60  # 72 hours


class InvitePharmacistRequest(BaseModel):
    """Invite a new pharmacist to join the current organization."""

    name: str = Field(min_length=2, max_length=200)
    email: EmailStr


@router.post("/invite", status_code=201)
def invite_pharmacist(
    request: InvitePharmacistRequest,
    current_user: UserDB = Depends(require_pharmacy_staff),
    db: Session = Depends(get_db),
):
    """
    Invite a new pharmacist to join the current organization.

    Creates an unverified, inactive account pre-linked to the
    current organization.  An invitation email is sent — the
    invitee follows the same email-verification flow used by
    normal registration.

    Security:
      - Only pharmacists already in an organization can invite.
      - The new account's organization_id is set from the *server*,
        not the client — an invitee cannot choose their org.
      - Passwords are not set by the inviting user; the invitee
        sets their own password via the invitation link.
      - Mandatory email verification is preserved.
    """

    if not current_user.organization_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Pharmacist is not associated with an organization",
        )

    normalized_email = request.email.lower().strip()

    # Prevent duplicate accounts.
    existing = (
        db.query(UserDB)
        .filter(UserDB.email == normalized_email)
        .first()
    )

    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this email already exists",
        )

    # Load the organization so we can include the name in the email.
    organization = (
        db.query(OrganizationDB)
        .filter(OrganizationDB.id == current_user.organization_id)
        .first()
    )

    # Generate a verification token — identical mechanism to
    # normal email verification.
    raw_token = generate_email_verification_token()
    token_hash = hash_email_verification_token(raw_token)
    expires_at = datetime.now(timezone.utc) + timedelta(
        minutes=INVITE_TOKEN_EXPIRE_MINUTES
    )

    # Create the account with a random placeholder password hash.
    # The invitee MUST set their own password before they can use
    # the account — that is handled on the accept-invite page.
    placeholder_password = generate_email_verification_token()

    new_user = UserDB(
        organization_id=current_user.organization_id,
        name=request.name.strip(),
        email=normalized_email,
        password_hash=hash_password(placeholder_password),
        role="pharmacist",
        email_verified=False,
        is_active=False,  # Only activated after email verification
        email_verification_token_hash=token_hash,
        email_verification_expires_at=expires_at,
    )

    db.add(new_user)

    try:
        db.commit()
        db.refresh(new_user)
    except Exception:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create invitation",
        )

    # Send invitation email using the existing verification email
    # infrastructure.  The invitee lands on /accept-invite where
    # they set a password and the token is consumed.
    try:
        send_invite_email(
            recipient_email=normalized_email,
            recipient_name=request.name.strip(),
            inviter_name=current_user.name,
            organization_name=(
                organization.name if organization else "your pharmacy"
            ),
            invite_token=raw_token,
        )

        new_user.email_verification_sent_at = datetime.now(timezone.utc)
        db.commit()

    except Exception:
        # Account was created — return a useful message even if
        # email fails; the invitee can request resend verification.
        return {
            "message": (
                "Invitation created but the email could not be sent. "
                "Ask the invitee to use 'Resend verification' with their email."
            ),
            "email": normalized_email,
            "email_sent": False,
        }

    return {
        "message": (
            f"Invitation sent to {normalized_email}. "
            "They will receive an email to set up their account."
        ),
        "email": normalized_email,
        "email_sent": True,
    }


def send_invite_email(
    recipient_email: str,
    recipient_name: str,
    inviter_name: str,
    organization_name: str,
    invite_token: str,
) -> None:
    """
    Send an invitation email to a new pharmacist.

    The invite flow reuses /accept-invite on the frontend,
    which collects a password and then submits the verification
    token via the existing /auth/verify-email endpoint.
    """
    import os
    import smtplib
    from email.message import EmailMessage

    frontend_url = os.getenv(
        "FRONTEND_URL",
        "http://localhost:3000",
    ).rstrip("/")

    accept_url = (
        f"{frontend_url}/accept-invite"
        f"?token={invite_token}"
        f"&email={recipient_email}"
    )

    display_name = recipient_name.strip() or "there"

    message = EmailMessage()
    message["Subject"] = (
        f"You're invited to join {organization_name} — Prescription Intelligence"
    )

    from backend.services.email_service import _get_smtp_config
    config = _get_smtp_config()
    message["From"] = config["from_email"]
    message["To"] = recipient_email

    text_body = f"""Hello {display_name},

{inviter_name} has invited you to join {organization_name} on Prescription Intelligence.

To accept the invitation and set up your account, visit:
{accept_url}

This invitation link will expire in 72 hours.

If you did not expect this invitation, you can safely ignore this email.

Regards,
Prescription Intelligence
"""

    html_body = f"""\
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>You're invited</title>
</head>
<body style="margin:0;padding:0;background:#F4F7F5;font-family:Arial,Helvetica,sans-serif;">
    <div style="max-width:620px;margin:40px auto;background:#FFFFFF;border:1px solid #DFE6E1;border-radius:12px;overflow:hidden;">
        <div style="padding:28px 32px;border-bottom:1px solid #DFE6E1;">
            <div style="font-size:13px;font-weight:700;letter-spacing:0.08em;color:#35664D;text-transform:uppercase;">
                Prescription Intelligence
            </div>
        </div>
        <div style="padding:32px;">
            <h1 style="margin:0 0 16px;color:#17211D;font-size:26px;line-height:1.25;">
                You&apos;re invited
            </h1>
            <p style="color:#526158;font-size:15px;line-height:1.6;">
                Hello {display_name},
            </p>
            <p style="color:#526158;font-size:15px;line-height:1.6;">
                <strong>{inviter_name}</strong> has invited you to join
                <strong>{organization_name}</strong> on Prescription Intelligence.
            </p>
            <div style="margin:28px 0;">
                <a href="{accept_url}" style="display:inline-block;padding:13px 22px;background:#35664D;color:#FFFFFF;text-decoration:none;border-radius:7px;font-size:14px;font-weight:700;">
                    Accept invitation
                </a>
            </div>
            <p style="color:#7C8881;font-size:13px;line-height:1.6;">
                This invitation link expires in 72 hours.
            </p>
            <p style="color:#7C8881;font-size:13px;line-height:1.6;">
                If the button does not work, copy this link into your browser:
            </p>
            <p style="color:#526158;font-size:12px;line-height:1.6;word-break:break-all;">
                {accept_url}
            </p>
            <p style="margin-top:28px;color:#7C8881;font-size:13px;line-height:1.6;">
                If you did not expect this invitation, you can safely ignore this email.
            </p>
        </div>
    </div>
</body>
</html>
"""

    message.set_content(text_body)
    message.add_alternative(html_body, subtype="html")

    with smtplib.SMTP(config["host"], config["port"], timeout=20) as server:
        server.ehlo()
        server.starttls()
        server.ehlo()
        server.login(config["username"], config["password"])
        server.send_message(message)
