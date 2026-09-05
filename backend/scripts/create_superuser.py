"""Create or promote a KOLIA superuser (role SALES_DIRECTOR).

Run inside the backend container:

    docker compose run --rm backend python scripts/create_superuser.py \
        --name "Ana" --email ana@empresa.com

The password is read from KOLIA_SUPERUSER_PASSWORD or prompted without echo;
it is never taken from argv, so it does not leak into shell history or `ps`.
Re-running for an existing email is a no-op unless --force is given.
"""
import argparse
import getpass
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pydantic import ValidationError
from sqlalchemy import select

from core.database import SessionLocal, init_database
from core.security import get_password_hash
from models.user import UserModel
from schemas.user import RoleEnum, UserCreate

MIN_PASSWORD, MAX_PASSWORD = 8, 72


def read_password() -> str:
    password = os.environ.get("KOLIA_SUPERUSER_PASSWORD")
    if password is None:
        if not sys.stdin.isatty():
            sys.exit("Defina KOLIA_SUPERUSER_PASSWORD ou rode com -it para digitar a senha.")
        password = getpass.getpass("Senha: ")
        if password != getpass.getpass("Confirme a senha: "):
            sys.exit("As senhas não conferem.")
    # bcrypt truncates past 72 bytes; schemas/user.py enforces the same window.
    if not MIN_PASSWORD <= len(password) <= MAX_PASSWORD:
        sys.exit(f"A senha deve ter entre {MIN_PASSWORD} e {MAX_PASSWORD} caracteres.")
    return password


def main() -> None:
    parser = argparse.ArgumentParser(description="Cria ou promove um superusuário KOLIA.")
    parser.add_argument("--name", required=True)
    parser.add_argument("--email", required=True)
    parser.add_argument("--role", default=RoleEnum.SALES_DIRECTOR.value,
                        choices=[role.value for role in RoleEnum])
    parser.add_argument("--force", action="store_true",
                        help="Atualiza senha e papel se o e-mail já existir.")
    args = parser.parse_args()

    password = read_password()
    # Validate through the same schema /register uses. Without this the script
    # could create a user that /login can never authenticate: EmailStr rejects
    # reserved domains such as .local, so the row existed but was unusable.
    try:
        email = UserCreate(name=args.name, email=args.email.strip(),
                           role=args.role, password=password).email.lower()
    except ValidationError as error:
        first = error.errors()[0]
        sys.exit(f"Dados inválidos ({'.'.join(str(p) for p in first['loc'])}): {first['msg']}")

    init_database()
    with SessionLocal() as db:
        user = db.scalar(select(UserModel).where(UserModel.email == email))
        if user is not None and not args.force:
            sys.exit(f"'{email}' já existe (papel {user.role.value}). Use --force para atualizar.")
        if user is None:
            user = UserModel(name=args.name, email=email)
            db.add(user)
            action = "criado"
        else:
            action = "atualizado"
        user.name = args.name
        user.role = RoleEnum(args.role)
        user.password = get_password_hash(password)
        db.commit()

    print(f"Superusuário {action}: {email} (papel {args.role})")


if __name__ == "__main__":
    main()
