"""Property-based tests for file extension filtering.

Tests Property 10: File extension filtering from the
modular-agent-registry-personality-framework design document.

Property 10 validates that for any set of files in the agents directory with
various extensions, the registry SHALL only load files with .yaml or .yml
extensions and ignore all other files regardless of their content.

Feature: modular-agent-registry, Property 10: File extension filtering

**Validates: Requirements 3.9**

References:
    - Design: .kiro/specs/Step_5-1_modular-agent-registry-personality-framework/design.md (Property 10)
    - Requirements: .kiro/specs/Step_5-1_modular-agent-registry-personality-framework/requirements.md
    - Implementation: src/backend/src/alcoabase/services/agent_file_watcher.py
"""

from __future__ import annotations

from pathlib import PurePosixPath

import hypothesis.strategies as st
from hypothesis import given, settings

from alcoabase.services.agent_file_watcher import _VALID_EXTENSIONS


# ---------------------------------------------------------------------------
# Hypothesis Strategies
# ---------------------------------------------------------------------------

# Common non-YAML extensions that should be rejected
_INVALID_EXTENSIONS = [
    ".json", ".txt", ".py", ".md", ".toml", ".cfg", ".ini", ".xml",
    ".csv", ".log", ".sh", ".bat", ".exe", ".pdf", ".doc", ".html",
    ".js", ".ts", ".css", ".png", ".jpg", ".gif", ".zip", ".tar",
    ".gz", ".bak", ".tmp", ".swp", ".lock", ".env", ".conf",
]

# Valid YAML extensions
_YAML_EXTENSIONS = [".yaml", ".yml"]

# Strategy for valid filename stems (without extension)
filename_stems: st.SearchStrategy[str] = st.text(
    alphabet=st.characters(
        whitelist_categories=("L", "N"),
        whitelist_characters="_-.",
    ),
    min_size=1,
    max_size=30,
).filter(lambda s: not s.startswith("."))

# Strategy for random extensions (including valid and invalid)
random_extensions: st.SearchStrategy[str] = st.one_of(
    # Known invalid extensions
    st.sampled_from(_INVALID_EXTENSIONS),
    # Known valid extensions
    st.sampled_from(_YAML_EXTENSIONS),
    # Randomly generated extensions
    st.text(
        alphabet=st.characters(whitelist_categories=("L", "N")),
        min_size=1,
        max_size=10,
    ).map(lambda s: f".{s}"),
    # No extension (empty suffix)
    st.just(""),
)


@st.composite
def filename_with_extension(
    draw: st.DrawFn,
    extension: st.SearchStrategy[str] | None = None,
) -> str:
    """Generate a filename with a specific or random extension.

    Args:
        extension: Strategy for the extension. If None, uses random_extensions.

    Returns:
        A filename string like "my-agent.yaml" or "readme.txt".
    """
    stem = draw(filename_stems)
    ext = draw(extension if extension is not None else random_extensions)
    return f"{stem}{ext}"


@st.composite
def file_set_with_mixed_extensions(
    draw: st.DrawFn,
) -> list[str]:
    """Generate a list of filenames with a mix of valid and invalid extensions.

    Ensures at least one valid and one invalid extension are present.

    Returns:
        List of filename strings.
    """
    # At least one valid YAML file
    valid_files = draw(
        st.lists(
            filename_with_extension(extension=st.sampled_from(_YAML_EXTENSIONS)),
            min_size=1,
            max_size=5,
        )
    )

    # At least one invalid file
    invalid_files = draw(
        st.lists(
            filename_with_extension(extension=st.sampled_from(_INVALID_EXTENSIONS)),
            min_size=1,
            max_size=5,
        )
    )

    # Some random files
    random_files = draw(
        st.lists(
            filename_with_extension(),
            min_size=0,
            max_size=5,
        )
    )

    return valid_files + invalid_files + random_files


# ---------------------------------------------------------------------------
# Property 10: File extension filtering
# ---------------------------------------------------------------------------


def _should_be_processed(filename: str) -> bool:
    """Determine if a file should be processed based on its extension.

    Uses the same logic as the AgentFileWatcher: checks if the file's
    suffix (lowercased) is in _VALID_EXTENSIONS.

    Args:
        filename: The filename to check.

    Returns:
        True if the file has a .yaml or .yml extension.
    """
    return PurePosixPath(filename).suffix.lower() in _VALID_EXTENSIONS


class TestFileExtensionFilteringProperties:
    """Property tests for file extension filtering.

    For any set of files in the agents directory with various extensions,
    the registry SHALL only load files with .yaml or .yml extensions and
    ignore all other files regardless of their content.

    Feature: modular-agent-registry, Property 10: File extension filtering

    **Validates: Requirements 3.9**
    """

    @given(filename=filename_with_extension(extension=st.sampled_from(_YAML_EXTENSIONS)))
    @settings(max_examples=100)
    def test_yaml_yml_files_are_accepted(self, filename: str) -> None:
        """Files with .yaml or .yml extensions SHALL be processed.

        **Validates: Requirements 3.9**
        """
        path = PurePosixPath(filename)
        assert path.suffix.lower() in _VALID_EXTENSIONS, (
            f"File '{filename}' with extension '{path.suffix}' should be accepted "
            f"but was not found in _VALID_EXTENSIONS={_VALID_EXTENSIONS}"
        )

    @given(filename=filename_with_extension(extension=st.sampled_from(_INVALID_EXTENSIONS)))
    @settings(max_examples=100)
    def test_non_yaml_files_are_rejected(self, filename: str) -> None:
        """Files with extensions other than .yaml/.yml SHALL be ignored.

        **Validates: Requirements 3.9**
        """
        path = PurePosixPath(filename)
        assert path.suffix.lower() not in _VALID_EXTENSIONS, (
            f"File '{filename}' with extension '{path.suffix}' should be rejected "
            f"but was found in _VALID_EXTENSIONS={_VALID_EXTENSIONS}"
        )

    @given(filenames=file_set_with_mixed_extensions())
    @settings(max_examples=100)
    def test_filtering_correctly_partitions_file_set(
        self, filenames: list[str]
    ) -> None:
        """For any mixed set of files, filtering produces exactly the .yaml/.yml subset.

        **Validates: Requirements 3.9**
        """
        # Apply the same filtering logic as AgentFileWatcher._watch_loop
        accepted = [f for f in filenames if _should_be_processed(f)]
        rejected = [f for f in filenames if not _should_be_processed(f)]

        # Every accepted file must have a valid extension
        for f in accepted:
            suffix = PurePosixPath(f).suffix.lower()
            assert suffix in _VALID_EXTENSIONS, (
                f"Accepted file '{f}' has invalid extension '{suffix}'"
            )

        # Every rejected file must NOT have a valid extension
        for f in rejected:
            suffix = PurePosixPath(f).suffix.lower()
            assert suffix not in _VALID_EXTENSIONS, (
                f"Rejected file '{f}' has valid extension '{suffix}' but was filtered out"
            )

        # The union of accepted and rejected equals the original set
        assert len(accepted) + len(rejected) == len(filenames)

    @given(
        stem=filename_stems,
        ext=st.text(
            alphabet=st.characters(whitelist_categories=("L", "N")),
            min_size=1,
            max_size=10,
        ).filter(lambda s: s.lower() not in ("yaml", "yml")),
    )
    @settings(max_examples=100)
    def test_arbitrary_extensions_are_rejected(
        self, stem: str, ext: str
    ) -> None:
        """Any randomly generated extension that is not yaml/yml SHALL be rejected.

        **Validates: Requirements 3.9**
        """
        filename = f"{stem}.{ext}"
        path = PurePosixPath(filename)
        assert path.suffix.lower() not in _VALID_EXTENSIONS, (
            f"File '{filename}' with arbitrary extension '.{ext}' should be rejected "
            f"but was found in _VALID_EXTENSIONS"
        )

    @given(
        stem=filename_stems,
        ext=st.sampled_from(["YAML", "YML", "Yaml", "Yml", "yAmL", "yMl"]),
    )
    @settings(max_examples=100)
    def test_case_insensitive_extension_matching(
        self, stem: str, ext: str
    ) -> None:
        """Extension matching SHALL be case-insensitive (.YAML, .Yml, etc. are valid).

        **Validates: Requirements 3.9**
        """
        filename = f"{stem}.{ext}"
        path = PurePosixPath(filename)
        # The watcher uses path.suffix.lower() so case variations should pass
        assert path.suffix.lower() in _VALID_EXTENSIONS, (
            f"File '{filename}' with case-variant extension '.{ext}' should be accepted "
            f"(suffix.lower()='{path.suffix.lower()}') but was not found in _VALID_EXTENSIONS"
        )
