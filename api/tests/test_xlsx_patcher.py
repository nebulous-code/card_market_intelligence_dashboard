"""Unit tests for ``services.xlsx_patcher``.

The happy path is already exercised end to end by
``test_collection_excel.py``, which patches the real template and reads
the result back. These tests cover what that fixture cannot reach:

* malformed or unusual packages (missing tables, unhosted tables,
  table parts with no ``displayName``, sheets with no ``sheetData``)
* the date and datetime cell encoding -- the collection fixtures never
  produce a historic row, so no date value reaches ``_cell_xml`` there
* ``_find_date_style_id`` against stylesheets with and without a
  usable date format

Packages are built by hand rather than loaded from a fixture file so
each defect can be introduced in isolation.
"""

import zipfile
from datetime import date, datetime, timezone
from decimal import Decimal
from io import BytesIO

import pytest

from services.xlsx_patcher import (
    _build_row,
    _cell_xml,
    _column_letter,
    _find_date_style_id,
    _index_tables,
    _numeric_cell,
    _replace_attr,
    _rewrite_sheet_data,
    patch_tables,
)

# Excel's serial for 2000-01-01 under the 1900 date system. Hard-coded
# rather than computed so a change to _EXCEL_EPOCH fails the test
# instead of silently moving both sides of the comparison.
SERIAL_2000_01_01 = 36526

SHEET_XML = (
    b'<?xml version="1.0"?>'
    b'<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
    b'<dimension ref="A1:B2"/>'
    b"<sheetData>"
    b'<row r="1">'
    b'<c r="A1" t="inlineStr"><is><t>name</t></is></c>'
    b'<c r="B1" t="inlineStr"><is><t>when</t></is></c>'
    b"</row>"
    b"</sheetData>"
    b"</worksheet>"
)

STYLES_WITH_DATE = (
    b'<?xml version="1.0"?>'
    b'<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
    b"<cellXfs count=\"2\">"
    b'<xf numFmtId="0" fontId="0" fillId="0" borderId="0"/>'
    b'<xf numFmtId="14" fontId="0" fillId="0" borderId="0" applyNumberFormat="1"/>'
    b"</cellXfs>"
    b"</styleSheet>"
)


def _table_xml(display_name: str | None) -> bytes:
    """A Table part. ``None`` omits displayName entirely."""
    attr = f' displayName="{display_name}"' if display_name else ""
    return (
        '<?xml version="1.0"?>'
        '<table xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"'
        f' id="1" name="t1"{attr} ref="A1:B2">'
        '<autoFilter ref="A1:B2"/>'
        "</table>"
    ).encode()


def _build_package(
    *,
    display_name: str | None = "widgets",
    host_sheet: bool = True,
    styles: bytes = STYLES_WITH_DATE,
) -> bytes:
    """Assemble a minimal .xlsx exercising the parts the patcher touches."""
    buf = BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("xl/worksheets/sheet1.xml", SHEET_XML)
        z.writestr("xl/tables/table1.xml", _table_xml(display_name))
        z.writestr("xl/styles.xml", styles)
        if host_sheet:
            z.writestr(
                "xl/worksheets/_rels/sheet1.xml.rels",
                '<?xml version="1.0"?>'
                '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/'
                'officeDocument/2006/relationships/table" Target="../tables/table1.xml"/>'
                "</Relationships>",
            )
    return buf.getvalue()


# ---------------------------------------------------------------------------
# patch_tables -- package-level failures
# ---------------------------------------------------------------------------


def test_patch_tables_unknown_table_name_raises():
    """A caller asking for a Table the template doesn't define is a
    programming error, not a data condition -- fail loudly rather than
    silently returning an unpatched workbook."""
    pkg = _build_package(display_name="widgets")
    with pytest.raises(KeyError, match="missing_table"):
        patch_tables(pkg, {"missing_table": (("name",), [])})


def test_patch_tables_table_without_host_sheet_raises():
    """A Table part with no worksheet relationship pointing at it cannot
    be written to -- there is no sheetData to rewrite."""
    pkg = _build_package(display_name="widgets", host_sheet=False)
    with pytest.raises(KeyError, match="widgets"):
        patch_tables(pkg, {"widgets": (("name",), [])})


def test_patch_tables_leaves_untargeted_parts_byte_identical():
    """Everything the patcher is not explicitly rewriting must survive
    untouched -- this is the property the whole module exists for.

    Two data rows are used so the Table ref genuinely has to grow; with
    a single row the fixture's existing A1:B2 ref is already correct and
    the part would be rewritten to identical bytes.
    """
    pkg = _build_package()
    rows = [{"name": "a"}, {"name": "b"}]
    out = patch_tables(pkg, {"widgets": (("name", "when"), rows)})

    src, dst = zipfile.ZipFile(BytesIO(pkg)), zipfile.ZipFile(BytesIO(out))
    assert set(src.namelist()) == set(dst.namelist())
    assert src.read("xl/styles.xml") == dst.read("xl/styles.xml")
    changed = {n for n in src.namelist() if src.read(n) != dst.read(n)}
    assert changed == {"xl/worksheets/sheet1.xml", "xl/tables/table1.xml"}

    # The ref must cover header + both data rows, on both the table and
    # its autoFilter, or Excel only treats the placeholder range as data.
    table = dst.read("xl/tables/table1.xml").decode()
    assert 'ref="A1:B3"' in table
    assert '<autoFilter ref="A1:B3"/>' in table


# ---------------------------------------------------------------------------
# _index_tables
# ---------------------------------------------------------------------------


def test_index_tables_skips_part_without_display_name():
    """Table parts lacking displayName are skipped rather than crashing
    the index build."""
    pkg = _build_package(display_name=None)
    with zipfile.ZipFile(BytesIO(pkg)) as z:
        assert _index_tables(z) == {}


def test_index_tables_maps_display_name_to_part():
    pkg = _build_package(display_name="widgets")
    with zipfile.ZipFile(BytesIO(pkg)) as z:
        assert _index_tables(z) == {"widgets": "xl/tables/table1.xml"}


# ---------------------------------------------------------------------------
# _find_date_style_id
# ---------------------------------------------------------------------------


def test_find_date_style_id_returns_none_without_cell_xfs():
    styles = b'<?xml version="1.0"?><styleSheet/>'
    assert _find_date_style_id(styles) is None


def test_find_date_style_id_returns_none_when_no_format_is_a_date():
    styles = (
        b"<styleSheet><cellXfs>"
        b'<xf numFmtId="0"/><xf numFmtId="2"/>'
        b"</cellXfs></styleSheet>"
    )
    assert _find_date_style_id(styles) is None


def test_find_date_style_id_finds_builtin_date_format():
    """numFmtId 14 is Excel's built-in short date."""
    assert _find_date_style_id(STYLES_WITH_DATE) == 1


def test_find_date_style_id_finds_custom_date_format():
    """A custom numFmt with date tokens and no time tokens counts."""
    styles = (
        b'<styleSheet><numFmt numFmtId="164" formatCode="yyyy-mm-dd"/>'
        b'<cellXfs><xf numFmtId="0"/><xf numFmtId="164"/></cellXfs></styleSheet>'
    )
    assert _find_date_style_id(styles) == 1


def test_find_date_style_id_rejects_datetime_format():
    """A format carrying time tokens is not a date format -- using it
    would render every date with a trailing 00:00:00."""
    styles = (
        b'<styleSheet><numFmt numFmtId="165" formatCode="yyyy-mm-dd hh:mm"/>'
        b'<cellXfs><xf numFmtId="165"/></cellXfs></styleSheet>'
    )
    assert _find_date_style_id(styles) is None


# ---------------------------------------------------------------------------
# _rewrite_sheet_data
# ---------------------------------------------------------------------------


def test_rewrite_sheet_data_without_sheet_data_element_raises():
    with pytest.raises(ValueError, match="sheetData"):
        _rewrite_sheet_data(b"<worksheet/>", ("name",), [], None)


def test_rewrite_sheet_data_without_header_row_raises():
    """The header row is preserved verbatim, so its absence means the
    sheet is not the shape the patcher assumes."""
    xml = b"<worksheet><sheetData></sheetData></worksheet>"
    with pytest.raises(ValueError, match="header row"):
        _rewrite_sheet_data(xml, ("name",), [], None)


def test_rewrite_sheet_data_preserves_header_and_replaces_body():
    out = _rewrite_sheet_data(SHEET_XML, ("name",), [{"name": "x"}], None)
    assert b"<is><t>name</t></is>" in out  # header untouched
    assert out.count(b"<row ") == 2  # header + one data row


# ---------------------------------------------------------------------------
# Cell encoding
# ---------------------------------------------------------------------------


def test_cell_xml_date_encodes_excel_serial():
    assert _cell_xml("A2", date(2000, 1, 1), None) == (
        f'<c r="A2"><v>{SERIAL_2000_01_01}</v></c>'
    )


def test_cell_xml_date_carries_style_when_one_exists():
    """Without the style attribute Excel shows the raw serial number
    instead of a date."""
    assert _cell_xml("A2", date(2000, 1, 1), 3) == (
        f'<c r="A2" s="3"><v>{SERIAL_2000_01_01}</v></c>'
    )


def test_cell_xml_datetime_encodes_fractional_serial():
    """Midday is half a day past the date's serial."""
    value = datetime(2000, 1, 1, 12, 0, 0)
    assert _cell_xml("B2", value, None) == (
        f'<c r="B2"><v>{SERIAL_2000_01_01 + 0.5}</v></c>'
    )


def test_cell_xml_datetime_is_offset_naive_safe():
    """A tz-aware datetime must not raise on the naive/aware subtraction
    -- midnight is built with the same tzinfo for that reason."""
    value = datetime(2000, 1, 1, 6, 0, 0, tzinfo=timezone.utc)
    assert _cell_xml("B2", value, None) == (
        f'<c r="B2"><v>{SERIAL_2000_01_01 + 0.25}</v></c>'
    )


def test_cell_xml_bool_precedes_int():
    """bool is a subclass of int; encoding True as a number would make
    Excel show 1 instead of TRUE."""
    assert _cell_xml("A2", True, None) == '<c r="A2" t="b"><v>1</v></c>'
    assert _cell_xml("A2", False, None) == '<c r="A2" t="b"><v>0</v></c>'


def test_cell_xml_decimal_is_written_as_number():
    assert _cell_xml("A2", Decimal("12.50"), None) == '<c r="A2"><v>12.5</v></c>'


def test_cell_xml_escapes_xml_metacharacters():
    """An unescaped ampersand in a card name would corrupt the sheet."""
    out = _cell_xml("A2", "Tom & Jerry <blue>", None)
    assert "&amp;" in out and "&lt;blue&gt;" in out


def test_numeric_cell_omits_style_attribute_when_none():
    assert _numeric_cell("A2", 1.5, None) == '<c r="A2"><v>1.5</v></c>'
    assert _numeric_cell("A2", 1.5, 7) == '<c r="A2" s="7"><v>1.5</v></c>'


def test_build_row_skips_missing_and_none_values():
    """Absent cells are how the patcher represents a blank -- writing an
    empty string instead would make Power Query see "" rather than null."""
    row = _build_row(2, ("a", "b", "c"), {"a": 1, "b": None}, None)
    assert b'r="A2"' in row
    assert b'r="B2"' not in row
    assert b'r="C2"' not in row


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------


def test_column_letter_rolls_over_past_z():
    assert _column_letter(1) == "A"
    assert _column_letter(26) == "Z"
    assert _column_letter(27) == "AA"
    assert _column_letter(52) == "AZ"
    assert _column_letter(53) == "BA"


def test_replace_attr_only_touches_first_match():
    xml = b'<table ref="A1:B2"><autoFilter ref="A1:B2"/></table>'
    out = _replace_attr(xml, b"table", b"ref", "A1:B9")
    assert b'<table ref="A1:B9">' in out
    assert b'<autoFilter ref="A1:B2"/>' in out
