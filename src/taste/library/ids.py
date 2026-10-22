import secrets

ALPHABET = "abcdefghijklmnopqrstuvwxyz234567"


def new_id(n: int = 6) -> str:
    return "".join(secrets.choice(ALPHABET) for _ in range(n))
