"""Invariants the shipped template asset must satisfy.

These do not test code. They inspect ``api/assets/collection_template.xlsx``
directly and assert the properties that are easy to lose while editing the
workbook by hand in Excel -- a query left without "refresh on open", a
slicer that was never wired to every pivot, or sample data left cached in
the presentation sheets after a build session.

Every one of these has been missed at least once during the build, and
none of them fail loudly: the workbook still opens, so the only symptom
is a recipient seeing stale or empty analysis. Catching them in CI is
cheaper than catching them by eye.

The file is read as the zip of XML it is, deliberately not through
openpyxl, which cannot model Power Query, slicers or pivot caches and
would drop exactly the parts under test.
"""

import base64
import re
import struct
import zipfile
from io import BytesIO

import pytest

from services.collection_excel import PATCHED_TABLE_NAMES, TEMPLATE_PATH

# Queries the workbook is built on. A missing name means a query was
# renamed or deleted, which silently breaks whichever sheet consumed it.
EXPECTED_QUERIES = {
    "qCollection",
    "qPrices",
    "qMultipliers",
    "qHistoric",
    "qCardsRanked",
    "qSetsRanked",
    "qUpgradeCost",
    "qHistoricValue",
}

# An Excel Table must contain at least one row, so a table holding no
# real data still reports a single blank one. Anything above this is
# cached data that would ship to a recipient.
MAX_SHIPPED_DATA_ROWS = 1


@pytest.fixture(scope="module")
def workbook() -> zipfile.ZipFile:
    if not TEMPLATE_PATH.exists():  # pragma: no cover - asset always present
        pytest.fail(f"template asset missing at {TEMPLATE_PATH}")
    return zipfile.ZipFile(BytesIO(TEMPLATE_PATH.read_bytes()))


def _data_row_count(table_ref: str) -> int:
    """Data rows covered by a Table ref like ``A1:M24`` or ``D10:M23``."""
    first, last = table_ref.split(":")
    return int(re.sub(r"\D", "", last)) - int(re.sub(r"\D", "", first))


def _tables(wb: zipfile.ZipFile) -> dict[str, str]:
    """displayName -> ref, for every Table part in the workbook."""
    out = {}
    for name in wb.namelist():
        if not re.fullmatch(r"xl/tables/table\d+\.xml", name):
            continue
        xml = wb.read(name).decode()
        display = re.search(r'displayName="([^"]+)"', xml)
        ref = re.search(r'<table[^>]*\bref="([^"]+)"', xml)
        if display and ref:
            out[display.group(1)] = ref.group(1)
    return out


def _pivot_cache_parts(wb: zipfile.ZipFile) -> list[str]:
    """Paths of every pivotCacheDefinition part, excluding its rels."""
    return sorted(
        n
        for n in wb.namelist()
        if "pivotCacheDefinition" in n and "_rels" not in n
    )


def _query_m_code(wb: zipfile.ZipFile) -> str:
    """The M source of every query, from the DataMashup blob."""
    raw = wb.read("customXml/item1.xml").decode("utf-16")
    encoded = re.search(r"<DataMashup[^>]*>(.*?)</DataMashup>", raw, re.DOTALL)
    assert encoded, "customXml/item1.xml is not a DataMashup package"
    blob = base64.b64decode(encoded.group(1))
    _version, length = struct.unpack("<II", blob[:8])
    with zipfile.ZipFile(BytesIO(blob[8 : 8 + length])) as pkg:
        return next(
            pkg.read(p).decode("utf-8", "replace")
            for p in pkg.namelist()
            if p.lower().endswith(".m")
        )


# ---------------------------------------------------------------------------
# Power Query survives and is complete
# ---------------------------------------------------------------------------


def test_power_query_part_is_present(workbook):
    """The customXml part is where Excel stores Power Query. Losing it
    means every derived sheet is dead on arrival."""
    assert "customXml/item1.xml" in workbook.namelist()


def test_all_expected_queries_exist(workbook):
    code = _query_m_code(workbook)
    found = set(re.findall(r'shared\s+#?"?([A-Za-z0-9_]+)"?\s*=', code))
    assert EXPECTED_QUERIES <= found, f"missing queries: {EXPECTED_QUERIES - found}"


# ---------------------------------------------------------------------------
# Refresh on open
# ---------------------------------------------------------------------------


def test_every_query_refreshes_on_open(workbook):
    """Without refreshOnLoad a query keeps whatever was cached at save
    time, so the sheet it feeds silently shows the previous session's
    numbers while everything around it updates."""
    xml = workbook.read("xl/connections.xml").decode()
    connections = re.findall(r'name="Query - ([^"]+)"', xml)
    refreshing = re.findall(
        r'name="Query - ([^"]+)"[^>]*refreshOnLoad="1"', xml
    )
    missing = [c for c in connections if c not in refreshing]
    assert not missing, f"connections without refresh-on-open: {missing}"


# ---------------------------------------------------------------------------
# Nothing ships with cached data
# ---------------------------------------------------------------------------


def test_the_four_patched_tables_exist(workbook):
    """patch_tables locates these by displayName. A rename in Excel would
    turn every export into a KeyError."""
    tables = _tables(workbook)
    missing = PATCHED_TABLE_NAMES - set(tables)
    assert not missing, f"patched tables missing from template: {missing}"


def test_no_table_ships_with_cached_data(workbook):
    """Source tables are cleared before shipping, but the tables that
    Power Query writes into keep their last refreshed contents. If those
    are not emptied too, a recipient who declines Enable Content sees a
    fully populated dashboard built from somebody else's collection.
    """
    offenders = {
        name: ref
        for name, ref in _tables(workbook).items()
        if _data_row_count(ref) > MAX_SHIPPED_DATA_ROWS
    }
    assert not offenders, (
        "tables still holding cached data (refresh with the source tables "
        f"empty, then save): {offenders}"
    )


def test_no_pivot_cache_ships_with_records(workbook):
    """Pivot caches store their own copy of the source rows. Clearing the
    tables does not clear the cache -- only a refresh does."""
    offenders = {}
    for name in _pivot_cache_parts(workbook):
        count = re.search(r'recordCount="(\d+)"', workbook.read(name).decode())
        if count and int(count.group(1)) > MAX_SHIPPED_DATA_ROWS:
            offenders[name.split("/")[-1]] = int(count.group(1))
    assert not offenders, f"pivot caches still holding records: {offenders}"


# ---------------------------------------------------------------------------
# Refresh on open, part two: the pivots
# ---------------------------------------------------------------------------


def test_every_pivot_cache_refreshes_on_open(workbook):
    """The connection-level refreshOnLoad only refreshes the queries. A
    pivot reading a refreshed table does not necessarily follow, so
    without this the workbook can open with live tables behind stale
    charts -- and it ships blank, so "stale" means empty.

    The flag lives on the cache, not the pivot, so setting it on any one
    pivot covers every pivot sharing that cache.
    """
    stale = []
    for name in _pivot_cache_parts(workbook):
        opening_tag = re.search(
            r"<pivotCacheDefinition\b[^>]*>", workbook.read(name).decode()
        ).group(0)
        if 'refreshOnLoad="1"' not in opening_tag:
            source = re.search(
                r'<worksheetSource[^>]*name="([^"]+)"', workbook.read(name).decode()
            )
            stale.append(
                f"{name.split('/')[-1]} (source {source.group(1) if source else '?'})"
            )
    assert not stale, "pivot caches without refresh-on-open: " + ", ".join(stale)


# ---------------------------------------------------------------------------
# Slicer wiring
# ---------------------------------------------------------------------------


def test_slicers_reach_every_pivot_on_their_cache(workbook):
    """A new slicer connects only to the pivot that was selected when it
    was inserted; the rest stay unticked. There is no error -- the slicer
    just moves one chart and looks broken to whoever clicks it.

    For each slicer, resolve the pivot cache its connected pivots belong
    to, then require it to reach every pivot sharing that cache.
    """
    pivot_cache_of: dict[str, str] = {}
    for name in workbook.namelist():
        if re.fullmatch(r"xl/pivotTables/pivotTable\d+\.xml", name):
            xml = workbook.read(name).decode()
            pivot_cache_of[re.search(r'name="([^"]+)"', xml).group(1)] = re.search(
                r'cacheId="(\d+)"', xml
            ).group(1)

    failures = []
    for name in workbook.namelist():
        if "slicerCaches/slicerCache" not in name or "_rels" in name:
            continue
        xml = workbook.read(name).decode()
        field = re.search(r'sourceName="([^"]+)"', xml).group(1)
        linked = set(re.findall(r'<pivotTable[^>]*name="([^"]+)"', xml))
        if not linked:
            continue
        caches = {pivot_cache_of[p] for p in linked if p in pivot_cache_of}
        expected = {p for p, c in pivot_cache_of.items() if c in caches}
        if linked != expected:
            failures.append(f"{field}: connected to {sorted(linked)}, expected {sorted(expected)}")

    assert not failures, "slicers not reaching every pivot on their cache: " + "; ".join(failures)
