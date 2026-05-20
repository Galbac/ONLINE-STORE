from passlib.context import CryptContext


class PasswordService:
    def __init__(self) -> None:
        self._password_context = CryptContext(
            schemes=["bcrypt"],
            deprecated="auto",
        )

    def hash_password(self, password: str) -> str:
        return self._password_context.hash(password)
