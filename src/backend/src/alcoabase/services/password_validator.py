"""Password validation service for GxP password policy enforcement."""

import re


class PasswordValidator:
    """Validates passwords against the GxP password policy.

    Policy rules:
        - Minimum 12 characters
        - At least one uppercase letter
        - At least one lowercase letter
        - At least one digit
        - At least one special character (non-alphanumeric)
    """

    MIN_LENGTH: int = 12

    def validate(self, password: str) -> list[str]:
        """Return list of unmet policy requirements (empty = valid).

        Args:
            password: The password string to validate.

        Returns:
            A list of human-readable strings describing each unmet
            policy requirement. An empty list means the password is valid.
        """
        errors: list[str] = []

        if len(password) < self.MIN_LENGTH:
            errors.append(
                f"Password must be at least {self.MIN_LENGTH} characters long"
            )

        if not re.search(r"[A-Z]", password):
            errors.append("Password must contain at least one uppercase letter")

        if not re.search(r"[a-z]", password):
            errors.append("Password must contain at least one lowercase letter")

        if not re.search(r"\d", password):
            errors.append("Password must contain at least one digit")

        if not re.search(r"[^a-zA-Z0-9]", password):
            errors.append("Password must contain at least one special character")

        return errors
