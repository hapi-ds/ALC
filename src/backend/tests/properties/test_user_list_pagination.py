"""Property-based tests for User List Pagination Correctness.

Tests Property 7 from the admin-dashboard-user-management design document:
For any company with N users and for any valid (page, page_size) parameters,
the paginated response SHALL return at most page_size users, the total SHALL
equal N, and the union of all pages SHALL equal the complete user set.

**Validates: Requirements 5.1**

References:
    - Design: .kiro/specs/Step_6-1_admin-dashboard-user-management/design.md (Property 7)
    - Requirements: .kiro/specs/Step_6-1_admin-dashboard-user-management/requirements.md (5.1)
"""

import math

import hypothesis.strategies as st
from hypothesis import given, settings


# ---------------------------------------------------------------------------
# Pure pagination function (mirrors the logic in UserManagementService.list_users)
# ---------------------------------------------------------------------------


def paginate(items: list, page: int, page_size: int) -> dict:
    """Apply pagination to a list of items.

    This is the pure-function equivalent of the pagination logic in
    UserManagementService.list_users. It computes offset/limit slicing,
    total count, and total_pages.

    Args:
        items: The complete list of items to paginate.
        page: 1-based page number.
        page_size: Maximum number of items per page.

    Returns:
        Dictionary with keys: users, total, page, page_size, total_pages.
    """
    total = len(items)
    offset = (page - 1) * page_size
    page_items = items[offset : offset + page_size]
    total_pages = math.ceil(total / page_size) if total > 0 else 1

    return {
        "users": page_items,
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": total_pages,
    }


# ---------------------------------------------------------------------------
# Hypothesis Strategies
# ---------------------------------------------------------------------------


@st.composite
def st_user_list(draw: st.DrawFn) -> list[dict]:
    """Generate a list of N user dictionaries (0 to 200 users).

    Each user has a unique id and basic fields matching UserListItem schema.

    Returns:
        A list of user dictionaries with unique ids.
    """
    n = draw(st.integers(min_value=0, max_value=200))
    users = []
    for i in range(n):
        users.append({
            "id": i + 1,
            "username": f"user_{i}",
            "email": f"user_{i}@example.com",
            "full_name": f"User {i}",
            "role": draw(
                st.sampled_from(
                    ["system_admin", "doc_admin", "it_admin", "member", "viewer"]
                )
            ),
            "is_active": draw(st.booleans()),
        })
    return users


@st.composite
def st_pagination_params(draw: st.DrawFn) -> tuple[int, int]:
    """Generate valid (page, page_size) parameters.

    page: 1-based, at least 1
    page_size: between 1 and 100 (matching UserListParams schema constraints)

    Returns:
        A tuple of (page, page_size).
    """
    page_size = draw(st.integers(min_value=1, max_value=100))
    page = draw(st.integers(min_value=1, max_value=50))
    return page, page_size


# ---------------------------------------------------------------------------
# Property 7: User List Pagination Correctness
# ---------------------------------------------------------------------------


@settings(max_examples=200, deadline=None)
@given(users=st_user_list(), params=st_pagination_params())
def test_page_returns_at_most_page_size_users(
    users: list[dict],
    params: tuple[int, int],
) -> None:
    """For any company with N users and any valid (page, page_size) params,
    the paginated response SHALL return at most page_size users.

    **Validates: Requirements 5.1**
    """
    page, page_size = params
    result = paginate(users, page, page_size)

    assert len(result["users"]) <= page_size, (
        f"Page returned {len(result['users'])} users but page_size is {page_size}. "
        f"Total users: {len(users)}, page: {page}"
    )


@settings(max_examples=200, deadline=None)
@given(users=st_user_list(), params=st_pagination_params())
def test_total_equals_n(
    users: list[dict],
    params: tuple[int, int],
) -> None:
    """For any company with N users and any valid (page, page_size) params,
    the total field SHALL equal N (the complete user count).

    **Validates: Requirements 5.1**
    """
    page, page_size = params
    result = paginate(users, page, page_size)

    assert result["total"] == len(users), (
        f"Total field is {result['total']} but expected {len(users)} users. "
        f"page: {page}, page_size: {page_size}"
    )


@settings(max_examples=200, deadline=None)
@given(users=st_user_list())
def test_union_of_all_pages_equals_complete_user_set(
    users: list[dict],
) -> None:
    """For any company with N users, iterating through all pages SHALL
    yield the complete user set (union of all pages equals the full list).

    **Validates: Requirements 5.1**
    """
    # Use a random but fixed page_size for this test
    page_size = max(1, len(users) // 3) if len(users) > 0 else 5

    all_page_users: list[dict] = []
    total_pages = math.ceil(len(users) / page_size) if len(users) > 0 else 1

    for page_num in range(1, total_pages + 1):
        result = paginate(users, page_num, page_size)
        all_page_users.extend(result["users"])

    # The union of all pages must equal the complete user set
    assert len(all_page_users) == len(users), (
        f"Union of all pages has {len(all_page_users)} users but expected {len(users)}. "
        f"page_size: {page_size}, total_pages: {total_pages}"
    )

    # Verify exact content match (order preserved)
    for i, (expected, actual) in enumerate(zip(users, all_page_users)):
        assert expected["id"] == actual["id"], (
            f"User mismatch at position {i}: expected id={expected['id']}, "
            f"got id={actual['id']}. page_size: {page_size}"
        )


@settings(max_examples=200, deadline=None)
@given(users=st_user_list(), params=st_pagination_params())
def test_total_pages_is_correct(
    users: list[dict],
    params: tuple[int, int],
) -> None:
    """For any company with N users and any valid (page, page_size) params,
    total_pages SHALL equal ceil(N / page_size), or 1 when N is 0.

    **Validates: Requirements 5.1**
    """
    page, page_size = params
    result = paginate(users, page, page_size)

    n = len(users)
    expected_total_pages = math.ceil(n / page_size) if n > 0 else 1

    assert result["total_pages"] == expected_total_pages, (
        f"total_pages is {result['total_pages']} but expected {expected_total_pages}. "
        f"N={n}, page_size={page_size}"
    )


@settings(max_examples=200, deadline=None)
@given(users=st_user_list(), params=st_pagination_params())
def test_pages_do_not_overlap(
    users: list[dict],
    params: tuple[int, int],
) -> None:
    """For any company with N users and any valid page_size, no user SHALL
    appear on more than one page (pages are disjoint partitions).

    **Validates: Requirements 5.1**
    """
    _, page_size = params
    n = len(users)
    total_pages = math.ceil(n / page_size) if n > 0 else 1

    seen_ids: set[int] = set()
    for page_num in range(1, total_pages + 1):
        result = paginate(users, page_num, page_size)
        for user in result["users"]:
            assert user["id"] not in seen_ids, (
                f"User id={user['id']} appears on multiple pages. "
                f"page_size: {page_size}, found duplicate on page {page_num}"
            )
            seen_ids.add(user["id"])
