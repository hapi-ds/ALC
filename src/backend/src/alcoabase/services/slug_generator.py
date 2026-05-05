"""Slug generation and validation service for URL-safe identifiers."""

import re
import unicodedata


class SlugGenerator:
    """Generates and validates URL-safe slugs.

    Slugs are lowercase alphanumeric strings with hyphens as separators.
    They are used as URL-safe identifiers for companies and other entities.
    """

    VALID_SLUG_PATTERN: re.Pattern[str] = re.compile(
        r"^[a-z0-9]+(?:-[a-z0-9]+)*$"
    )

    def generate(self, display_name: str) -> str:
        """Generate a URL-safe slug from a display name.

        Applies unicode normalization (NFKD), strips combining marks,
        converts to lowercase, replaces non-alphanumeric characters with
        hyphens, collapses consecutive hyphens, and strips leading/trailing
        hyphens.

        Args:
            display_name: The human-readable name to convert into a slug.

        Returns:
            A URL-safe slug string. Returns "untitled" if the input
            produces an empty result after processing.
        """
        # Normalize unicode: NFKD decomposition, then strip combining marks
        normalized = unicodedata.normalize("NFKD", display_name)
        ascii_text = "".join(
            char for char in normalized if not unicodedata.combining(char)
        )

        # Convert to lowercase
        slug = ascii_text.lower()

        # Replace any non-alphanumeric character with a hyphen
        slug = re.sub(r"[^a-z0-9]", "-", slug)

        # Collapse multiple consecutive hyphens into one
        slug = re.sub(r"-+", "-", slug)

        # Strip leading and trailing hyphens
        slug = slug.strip("-")

        # Fallback for empty results
        if not slug:
            return "untitled"

        return slug

    def validate(self, slug: str) -> bool:
        """Return True if slug contains only valid characters.

        A valid slug matches the pattern: lowercase letters, digits,
        and single hyphens between alphanumeric segments.

        Args:
            slug: The slug string to validate.

        Returns:
            True if the slug matches the valid pattern, False otherwise.
        """
        return bool(self.VALID_SLUG_PATTERN.match(slug))
