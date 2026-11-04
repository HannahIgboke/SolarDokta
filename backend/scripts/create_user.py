"""Create a dashboard login: a technician/admin (staff) or a customer linked to their site.

Usage (from backend/):
    python -m scripts.create_user --email tech@solardokta.test --role staff --name "Tunde (technician)"
    python -m scripts.create_user --email ada@solardokta.test --role customer --name "Ada Okafor" \\
        --site lagos-001 --lang pcm --whatsapp +2348012345678
    python -m scripts.create_user --list

You are asked for the password (it isn't shown or saved anywhere except Supabase Auth).
Running it again for the same email updates the profile (and the password if you give one).
The account is confirmed straight away, so no email is sent.
"""

import argparse
import getpass

from app.db import get_client

DEFAULT_ORG = "00000000-0000-0000-0000-000000000001"     # the demo installer from seed.sql


def find_user(client, email: str):
    page = 1
    while True:
        users = client.auth.admin.list_users(page=page, per_page=200)
        for u in users:
            if (u.email or "").lower() == email.lower():
                return u
        if len(users) < 200:
            return None
        page += 1


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--email")
    p.add_argument("--role", choices=["staff", "customer"])
    p.add_argument("--name", default="")
    p.add_argument("--site", help="customer: the site code they own, e.g. lagos-001")
    p.add_argument("--lang", choices=["en", "pcm"], default="en")
    p.add_argument("--whatsapp", help="E.164 number, e.g. +2348012345678")
    p.add_argument("--list", action="store_true", help="show existing profiles")
    args = p.parse_args()
    client = get_client()

    if args.list:
        sites = client.table("sites").select("code,customer_id").execute().data
        owned = {}
        for s in sites:
            owned.setdefault(s["customer_id"], []).append(s["code"])
        for r in client.table("profiles").select("*").order("role").execute().data:
            print(f"{r['role']:<9} {r.get('full_name') or '':<24} {r.get('preferred_language')}  "
                  f"{r.get('whatsapp_number') or '':<15} sites: {', '.join(owned.get(r['id'], [])) or '-'}")
        return
    if not args.email or not args.role:
        p.error("--email and --role are needed")

    site = None
    if args.role == "customer":
        if not args.site:
            p.error("a customer needs --site")
        rows = client.table("sites").select("id,org_id,code").eq("code", args.site).execute().data
        if not rows:
            p.error(f"no site {args.site!r}")
        site = rows[0]

    existing = find_user(client, args.email)
    password = getpass.getpass("Password (leave empty to keep the current one): " if existing
                               else "Password (at least 8 characters): ")
    if existing:
        user_id = existing.id
        if password:
            client.auth.admin.update_user_by_id(user_id, {"password": password})
        print(f"Updating existing user {args.email}")
    else:
        if len(password) < 8:
            p.error("use a password of at least 8 characters")
        user_id = client.auth.admin.create_user(
            {"email": args.email, "password": password, "email_confirm": True}).user.id
        print(f"Created user {args.email}")

    client.table("profiles").upsert({
        "id": user_id, "org_id": site["org_id"] if site else DEFAULT_ORG, "role": args.role,
        "full_name": args.name or None, "preferred_language": args.lang,
        "whatsapp_number": args.whatsapp,
    }, on_conflict="id").execute()
    if site:
        client.table("sites").update({"customer_id": user_id}).eq("id", site["id"]).execute()
        print(f"Linked to site {site['code']}")
    print(f"Profile saved: {args.role}")


if __name__ == "__main__":
    main()
