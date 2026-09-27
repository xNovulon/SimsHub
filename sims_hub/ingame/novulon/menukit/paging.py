"""Pure Python, no game imports (SPEC.md `menukit/` §4/§5.3, citing `gaps.md` §B.2).

`gaps.md` §B.2 checked `ui_dialog_picker.pyc`'s full outline directly and found no native row-count
ceiling on a picker message, while this audience's saves routinely exceed the game's own ~670-800-Sim
self-culling ceiling (players who install an MCCC-replacement mod skew hard toward "no culling"
saves). So paging is a hard v1 requirement, not polish, and it has to happen on the FILTERED list, not
the full Sim table - callers filter/search first, then call `page_of()` on the result. Page size
60-100 rows per SPEC.md §4.
"""

DEFAULT_PAGE_SIZE = 80
MIN_PAGE_SIZE = 60
MAX_PAGE_SIZE = 100


def page_of(items, page_size=DEFAULT_PAGE_SIZE, page_index=0):
    """(rows, has_prev, has_next) for `items` (any sequence) sliced at `page_index` (0-based).

    `page_index` is clamped into range rather than raising, so a stale index (the underlying list
    shrank - a Sim got deleted, a filter narrowed the results) never blows up a re-render; it just
    lands on the nearest valid page. Never builds anything beyond one page_size slice.
    """
    items = items if isinstance(items, (list, tuple)) else list(items)
    n = len(items)
    if n == 0 or page_size <= 0:
        return [], False, False
    last_index = (n - 1) // page_size
    if page_index < 0:
        page_index = 0
    elif page_index > last_index:
        page_index = last_index
    start = page_index * page_size
    end = start + page_size
    return list(items[start:end]), page_index > 0, end < n


def page_count(n_items, page_size=DEFAULT_PAGE_SIZE):
    """How many pages `n_items` split into at `page_size` (at least 1, even for an empty list, so a
    'Page 1 of 1' footer never has to special-case zero results)."""
    if page_size <= 0:
        return 1
    return max(1, (n_items + page_size - 1) // page_size)


def footer_text(n_items, page_size=DEFAULT_PAGE_SIZE, page_index=0):
    """'Page 1 of 3 (1-60 of 148)' - SPEC.md §5.3's exact footer copy shape. 1-based for display."""
    total_pages = page_count(n_items, page_size)
    page_index = max(0, min(page_index, total_pages - 1))
    if n_items == 0:
        return 'Page 1 of 1 (0 of 0)'
    start = page_index * page_size + 1
    end = min(n_items, start + page_size - 1)
    return 'Page %d of %d (%d-%d of %d)' % (page_index + 1, total_pages, start, end, n_items)
