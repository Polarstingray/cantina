'''
manage.py
    Small admin CLI for cantina. Run from backend/src/ (honors CANTINA_DATA_DIR
    just like the app, so point it at the same data dir the server uses):

        python manage.py create-user --email you@example.com --role admin
        python manage.py list-users

    There is no public signup yet, so this is how the first admin is created;
    after that, an admin can add family members from the app (POST /auth/users).
'''

import argparse
import getpass
import sys

import auth
import db


def cmd_create_user(args) :
    password = args.password or getpass.getpass("password: ")
    if not password :
        print("error: password required", file=sys.stderr)
        return 1
    try :
        uid = auth.create_user(args.email, password, args.role, args.household)
    except ValueError as e :
        print(f"error: {e}", file=sys.stderr)
        return 1
    hid = args.household or db.HOUSEHOLD_ID
    print(f"created user id={uid} email={args.email.strip().lower()} role={args.role} household={hid}")
    return 0


def cmd_list_users(args) :
    hid = args.household or db.HOUSEHOLD_ID
    users = auth.list_users(hid)
    if not users :
        print(f"(no users in household {hid})")
        return 0
    for u in users :
        print(f"  #{u['id']:<3} {u['role']:<6} {u['email']}  (since {u['created_at']})")
    return 0


def main() :
    p = argparse.ArgumentParser(description="cantina admin CLI")
    sub = p.add_subparsers(dest="cmd", required=True)

    c = sub.add_parser("create-user", help="create a user")
    c.add_argument("--email", required=True)
    c.add_argument("--password", help="omit to be prompted (keeps it out of shell history)")
    c.add_argument("--role", choices=["admin", "member"], default="member")
    c.add_argument("--household", type=int, default=None, help="household id (default 1)")
    c.set_defaults(func=cmd_create_user)

    l = sub.add_parser("list-users", help="list users in a household")
    l.add_argument("--household", type=int, default=None, help="household id (default 1)")
    l.set_defaults(func=cmd_list_users)

    args = p.parse_args()
    sys.exit(args.func(args))


if __name__ == "__main__" :
    main()
