"""Property-based tests for default audit profile uniqueness.

Tests Property 10 from the Multi-Agent Always-On Auditing design document:
- For any company, there SHALL be at most one audit profile with
  is_default=true at any time. Setting a new default SHALL unset the
  previous default atomically.

**Validates: Requirements 4.2**

References:
    - Design: .kiro/specs/Step_5-2_multi-agent-always-on-auditing/design.md
      (Correctness Property 10)
    - Requirements: .kiro/specs/Step_5-2_multi-agent-always-on-auditing/requirements.md
      (Requirement 4.2)
"""

from __future__ import annotations

from dataclasses import dataclass, field

import hypothesis.strategies as st
from hypothesis import given, settings
from hypothesis.stateful import (
    Bundle,
    RuleBasedStateMachine,
    initialize,
    rule,
)


# ---------------------------------------------------------------------------
# Lightweight model simulating AuditProfile default logic
# ---------------------------------------------------------------------------


@dataclass
class ProfileRecord:
    """Lightweight representation of an audit profile for testing.

    Attributes:
        id: Profile identifier.
        company_id: Owning company.
        is_default: Whether this is the company's default profile.
        is_active: Whether the profile is active (not soft-deleted).
    """

    id: int
    company_id: int
    is_default: bool
    is_active: bool = True


class DefaultProfileManager:
    """Simulates the default profile uniqueness logic from AuditProfileService.

    This mirrors the exact logic of:
    - AuditProfileService.create_profile (default enforcement)
    - AuditProfileService.update_profile (default switching)
    - AuditProfileService._unset_existing_default (atomic unset)

    The implementation is intentionally kept close to the service code
    to validate the invariant holds under arbitrary operation sequences.
    """

    def __init__(self) -> None:
        """Initialize with empty profile store."""
        self._profiles: list[ProfileRecord] = []
        self._next_id: int = 1

    def create_profile(self, company_id: int, is_default: bool) -> int:
        """Create a profile, enforcing single default per company.

        Mirrors AuditProfileService.create_profile logic:
        if is_default=True, unset existing default first.

        Args:
            company_id: The company this profile belongs to.
            is_default: Whether this should be the default profile.

        Returns:
            The ID of the created profile.
        """
        if is_default:
            self._unset_existing_default(company_id)

        profile = ProfileRecord(
            id=self._next_id,
            company_id=company_id,
            is_default=is_default,
            is_active=True,
        )
        self._profiles.append(profile)
        self._next_id += 1
        return profile.id

    def update_profile_default(
        self, profile_id: int, company_id: int, is_default: bool
    ) -> bool:
        """Update a profile's is_default flag, enforcing uniqueness.

        Mirrors AuditProfileService.update_profile logic:
        if setting is_default=True on a non-default profile, unset
        the existing default first.

        Args:
            profile_id: The profile to update.
            company_id: The company scope.
            is_default: New value for is_default.

        Returns:
            True if the profile was found and updated, False otherwise.
        """
        profile = self._get_active_profile(profile_id, company_id)
        if profile is None:
            return False

        if is_default and not profile.is_default:
            self._unset_existing_default(company_id)

        profile.is_default = is_default
        return True

    def delete_profile(self, profile_id: int, company_id: int) -> bool:
        """Soft-delete a profile by setting is_active=False.

        Args:
            profile_id: The profile to delete.
            company_id: The company scope.

        Returns:
            True if the profile was found and deleted, False otherwise.
        """
        profile = self._get_active_profile(profile_id, company_id)
        if profile is None:
            return False
        profile.is_active = False
        return True

    def count_defaults(self, company_id: int) -> int:
        """Count active default profiles for a company.

        Args:
            company_id: The company to check.

        Returns:
            Number of active profiles with is_default=True.
        """
        return sum(
            1
            for p in self._profiles
            if p.company_id == company_id and p.is_default and p.is_active
        )

    def _unset_existing_default(self, company_id: int) -> None:
        """Unset the current default profile for a company.

        Mirrors AuditProfileService._unset_existing_default.

        Args:
            company_id: The company whose default to unset.
        """
        for p in self._profiles:
            if (
                p.company_id == company_id
                and p.is_default
                and p.is_active
            ):
                p.is_default = False
                break  # At most one default should exist

    def _get_active_profile(
        self, profile_id: int, company_id: int
    ) -> ProfileRecord | None:
        """Get an active profile by ID and company.

        Args:
            profile_id: The profile ID.
            company_id: The company scope.

        Returns:
            The profile if found and active, else None.
        """
        for p in self._profiles:
            if (
                p.id == profile_id
                and p.company_id == company_id
                and p.is_active
            ):
                return p
        return None


# ---------------------------------------------------------------------------
# Hypothesis Strategies
# ---------------------------------------------------------------------------


@st.composite
def st_profile_creation_sequence(draw: st.DrawFn) -> list[bool]:
    """Generate a sequence of is_default flags for profile creations.

    Ensures at least one profile has is_default=True to make the test
    exercise the default enforcement logic.

    Returns:
        List of booleans representing is_default for each profile creation.
    """
    length = draw(st.integers(min_value=2, max_value=15))
    flags = draw(
        st.lists(st.booleans(), min_size=length, max_size=length).filter(
            lambda xs: any(xs)
        )
    )
    return flags


# ---------------------------------------------------------------------------
# Property 10: Default audit profile uniqueness
# ---------------------------------------------------------------------------


# Feature: Step_5-2_multi-agent-always-on-auditing, Property 10: Default audit profile uniqueness
@settings(max_examples=100, deadline=None)
@given(is_default_flags=st_profile_creation_sequence())
def test_default_profile_uniqueness_after_creation_sequence(
    is_default_flags: list[bool],
) -> None:
    """For any sequence of profile creations with varying is_default flags,
    at most one active profile per company SHALL have is_default=True at
    any point in time.

    This test creates multiple profiles in sequence, some with is_default=True,
    and verifies the invariant holds after each creation.

    **Validates: Requirements 4.2**
    """
    manager = DefaultProfileManager()
    company_id = 1

    for is_default in is_default_flags:
        manager.create_profile(company_id=company_id, is_default=is_default)

        # Invariant: at most one default per company after each creation
        default_count = manager.count_defaults(company_id)
        assert default_count <= 1, (
            f"Found {default_count} default profiles for company "
            f"{company_id} after creation. Expected at most 1."
        )


# Feature: Step_5-2_multi-agent-always-on-auditing, Property 10: Default audit profile uniqueness
@settings(max_examples=100, deadline=None)
@given(
    num_profiles=st.integers(min_value=2, max_value=10),
    update_targets=st.lists(
        st.integers(min_value=0, max_value=9), min_size=1, max_size=15
    ),
)
def test_default_profile_uniqueness_after_update_sequence(
    num_profiles: int,
    update_targets: list[int],
) -> None:
    """For any sequence of update_profile calls setting is_default=True on
    different profiles, at most one active profile per company SHALL have
    is_default=True after each update.

    **Validates: Requirements 4.2**
    """
    manager = DefaultProfileManager()
    company_id = 1

    # Create N profiles, all non-default initially
    profile_ids = []
    for _ in range(num_profiles):
        pid = manager.create_profile(company_id=company_id, is_default=False)
        profile_ids.append(pid)

    # Apply a sequence of updates setting various profiles as default
    for target_idx in update_targets:
        profile_id = profile_ids[target_idx % num_profiles]
        manager.update_profile_default(
            profile_id=profile_id,
            company_id=company_id,
            is_default=True,
        )

        # Invariant: at most one default per company after each update
        default_count = manager.count_defaults(company_id)
        assert default_count <= 1, (
            f"After setting profile {profile_id} as default, "
            f"found {default_count} default profiles for company "
            f"{company_id}. Expected at most 1."
        )


# Feature: Step_5-2_multi-agent-always-on-auditing, Property 10: Default audit profile uniqueness
@settings(max_examples=50, deadline=None)
@given(
    num_companies=st.integers(min_value=2, max_value=5),
    profiles_per_company=st.integers(min_value=2, max_value=6),
)
def test_default_profile_uniqueness_multi_company_isolation(
    num_companies: int,
    profiles_per_company: int,
) -> None:
    """For any number of companies each creating profiles with is_default=True,
    the default uniqueness constraint SHALL be enforced independently per
    company. Setting a default in company A SHALL NOT affect company B.

    **Validates: Requirements 4.2**
    """
    manager = DefaultProfileManager()

    # For each company, create multiple profiles all with is_default=True
    for company_id in range(1, num_companies + 1):
        for _ in range(profiles_per_company):
            manager.create_profile(company_id=company_id, is_default=True)

            # Invariant per company: at most one default
            default_count = manager.count_defaults(company_id)
            assert default_count <= 1, (
                f"Company {company_id} has {default_count} default "
                f"profiles. Expected at most 1."
            )

    # Final cross-company check: each company has exactly one default
    # (the last profile created with is_default=True for each company)
    for company_id in range(1, num_companies + 1):
        default_count = manager.count_defaults(company_id)
        assert default_count == 1, (
            f"Company {company_id} should have exactly 1 default "
            f"profile after all creations, but has {default_count}."
        )


# ---------------------------------------------------------------------------
# Stateful test: interleaved create/update/delete operations
# ---------------------------------------------------------------------------


class DefaultProfileStateMachine(RuleBasedStateMachine):
    """Stateful property test for default profile uniqueness.

    Generates arbitrary sequences of create, update, and delete operations
    across multiple companies and verifies the at-most-one-default invariant
    holds after every operation.

    **Validates: Requirements 4.2**
    """

    def __init__(self) -> None:
        """Initialize the state machine with a fresh manager."""
        super().__init__()
        self.manager = DefaultProfileManager()
        self.company_ids: list[int] = [1, 2, 3]
        self.created_profiles: dict[int, list[int]] = {
            cid: [] for cid in self.company_ids
        }

    @initialize()
    def init_profiles(self) -> None:
        """Seed each company with at least one profile."""
        for company_id in self.company_ids:
            pid = self.manager.create_profile(
                company_id=company_id, is_default=False
            )
            self.created_profiles[company_id].append(pid)

    @rule(
        company_id=st.sampled_from([1, 2, 3]),
        is_default=st.booleans(),
    )
    def create_profile(self, company_id: int, is_default: bool) -> None:
        """Create a profile and verify the invariant."""
        pid = self.manager.create_profile(
            company_id=company_id, is_default=is_default
        )
        self.created_profiles[company_id].append(pid)
        self._check_invariant()

    @rule(
        company_id=st.sampled_from([1, 2, 3]),
        is_default=st.booleans(),
        target_index=st.integers(min_value=0, max_value=100),
    )
    def update_profile_default(
        self, company_id: int, is_default: bool, target_index: int
    ) -> None:
        """Update a profile's default flag and verify the invariant."""
        profiles = self.created_profiles[company_id]
        if not profiles:
            return
        profile_id = profiles[target_index % len(profiles)]
        self.manager.update_profile_default(
            profile_id=profile_id,
            company_id=company_id,
            is_default=is_default,
        )
        self._check_invariant()

    @rule(
        company_id=st.sampled_from([1, 2, 3]),
        target_index=st.integers(min_value=0, max_value=100),
    )
    def delete_profile(self, company_id: int, target_index: int) -> None:
        """Soft-delete a profile and verify the invariant."""
        profiles = self.created_profiles[company_id]
        if not profiles:
            return
        profile_id = profiles[target_index % len(profiles)]
        self.manager.delete_profile(
            profile_id=profile_id, company_id=company_id
        )
        self._check_invariant()

    def _check_invariant(self) -> None:
        """Verify at most one default per company after every operation."""
        for company_id in self.company_ids:
            default_count = self.manager.count_defaults(company_id)
            assert default_count <= 1, (
                f"INVARIANT VIOLATED: Company {company_id} has "
                f"{default_count} default profiles. Expected at most 1."
            )


# Feature: Step_5-2_multi-agent-always-on-auditing, Property 10: Default audit profile uniqueness
TestDefaultProfileStateful = DefaultProfileStateMachine.TestCase
TestDefaultProfileStateful.settings = settings(
    max_examples=100, stateful_step_count=20, deadline=None
)
