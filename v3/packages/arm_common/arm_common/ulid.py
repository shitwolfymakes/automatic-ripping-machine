from ulid import ULID


def new_id(prefix: str) -> str:
    return f"{prefix}_{ULID()}"
