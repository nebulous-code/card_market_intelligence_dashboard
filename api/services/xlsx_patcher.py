"""
Drop row data into named Tables in a pre-built .xlsx without going
through openpyxl.

openpyxl rebuilds the .xlsx zip from its in-memory model on save and
silently drops parts it doesn't model -- Power Query, slicers, pivot
caches, certain chart features. For this project the workbook is the
user-facing portfolio artifact and is meant to be richly designed in
Excel, so the load+save round-trip is unacceptable.

This module treats the .xlsx as what it is on disk: a zip of XML. It
locates each target Table by ``displayName`` in ``xl/tables/tableN.xml``,
finds the sheet that hosts it through the worksheet rels, rewrites that
sheet's ``<sheetData>`` (preserving the header row verbatim), and
updates the Table's ``ref`` / ``autoFilter`` ref. Every other part is
copied through byte-for-byte.

The caller passes a mapping of table name to ``(columns, rows)``.
Columns are written in the given order starting at column A. Each row
dict is looked up by column name; ``None`` or missing values produce
empty cells.

Date cells get a style attribute pointing at a date-formatted
``cellXfs`` entry from ``xl/styles.xml`` when one is available, so they
display as dates rather than as the underlying Excel serial number.
"""

from __future__ import annotations

import re
import zipfile
from datetime import date, datetime
from decimal import Decimal
from io import BytesIO
from typing import Any, Sequence
from xml.sax.saxutils import escape as xml_escape

# Excel's "1900 date system" actually anchors at 1899-12-30 because of
# the historical Lotus 1-2-3 leap-year bug it preserves.
_EXCEL_EPOCH = date(1899, 12, 30)

# Built-in numFmtIds reserved for date/time formats (Microsoft spec).
_BUILTIN_DATE_FMT_IDS = {"14", "15", "16", "17", "22"}


def patch_tables(
    template_bytes: bytes,
    table_data: dict[str, tuple[Sequence[str], list[dict[str, Any]]]],
) -> bytes:
    """Patch named Tables in an .xlsx template with new row data.

    ``table_data`` maps Table displayName -> (column names in order,
    list of row dicts). Returns the bytes of the modified .xlsx.

    Raises ``KeyError`` if any requested Table name is not found in the
    template, or if a Table has no host sheet.
    """
    with zipfile.ZipFile(BytesIO(template_bytes)) as src:
        table_index = _index_tables(src)
        sheet_for_table = _index_sheet_hosts(src)
        date_style_id = _find_date_style_id(_read(src, "xl/styles.xml"))

        modified: dict[str, bytes] = {}
        for tbl_name, (columns, rows) in table_data.items():
            if tbl_name not in table_index:
                raise KeyError(f"Table {tbl_name!r} not found in template")
            table_part = table_index[tbl_name]
            sheet_part = sheet_for_table.get(table_part)
            if sheet_part is None:
                raise KeyError(f"No sheet hosts table {tbl_name!r}")

            data_row_count = max(1, len(rows))  # Tables require >= 1 data row
            last_ref = f"A1:{_column_letter(len(columns))}{1 + data_row_count}"

            sheet_xml = modified.get(sheet_part, _read(src, sheet_part))
            sheet_xml = _rewrite_sheet_data(sheet_xml, columns, rows, date_style_id)
            sheet_xml = _replace_attr(sheet_xml, b"dimension", b"ref", last_ref)
            modified[sheet_part] = sheet_xml

            table_xml = modified.get(table_part, _read(src, table_part))
            table_xml = _replace_attr(table_xml, b"table", b"ref", last_ref)
            table_xml = _replace_attr(table_xml, b"autoFilter", b"ref", last_ref)
            modified[table_part] = table_xml

        out = BytesIO()
        with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zout:
            for item in src.infolist():
                data = modified.get(item.filename) or src.read(item.filename)
                zout.writestr(item, data)
    return out.getvalue()


# ---------------------------------------------------------------------------
# Indexing
# ---------------------------------------------------------------------------


def _index_tables(src: zipfile.ZipFile) -> dict[str, str]:
    """displayName -> path of the table part (xl/tables/tableN.xml)."""
    out: dict[str, str] = {}
    for name in src.namelist():
        if not (name.startswith("xl/tables/") and name.endswith(".xml")):
            continue
        m = re.search(rb'displayName="([^"]+)"', src.read(name))
        if m:
            out[m.group(1).decode()] = name
    return out


def _index_sheet_hosts(src: zipfile.ZipFile) -> dict[str, str]:
    """Path of table part -> path of the sheet that references it."""
    out: dict[str, str] = {}
    for rels_name in src.namelist():
        if not (
            rels_name.startswith("xl/worksheets/_rels/sheet")
            and rels_name.endswith(".xml.rels")
        ):
            continue
        sheet_name = rels_name.replace("/_rels/", "/").removesuffix(".rels")
        rels_data = src.read(rels_name).decode()
        for m in re.finditer(r'Target="\.\./tables/([^"]+)"', rels_data):
            out["xl/tables/" + m.group(1)] = sheet_name
    return out


def _find_date_style_id(styles_xml: bytes) -> int | None:
    """Index into <cellXfs> of an entry using a date numFmt, or None.

    Recognises both built-in date numFmtIds and custom numFmts whose
    format code contains date tokens (y/m/d) without time tokens, which
    is the heuristic Excel itself uses to classify a format as a date.
    """
    date_fmt_ids = set(_BUILTIN_DATE_FMT_IDS)
    for m in re.finditer(
        rb'<numFmt[^>]*numFmtId="(\d+)"[^>]*formatCode="([^"]+)"', styles_xml
    ):
        fmt_id = m.group(1).decode()
        code = m.group(2).decode().lower()
        if any(ch in code for ch in "ymd") and "h" not in code and "s" not in code:
            date_fmt_ids.add(fmt_id)

    xfs = re.search(rb"<cellXfs[^>]*>(.*?)</cellXfs>", styles_xml, re.DOTALL)
    if not xfs:
        return None
    for idx, xf in enumerate(
        re.finditer(rb"<xf\b[^/]*?(?:/>|>.*?</xf>)", xfs.group(1), re.DOTALL)
    ):
        m = re.search(rb'numFmtId="(\d+)"', xf.group(0))
        if m and m.group(1).decode() in date_fmt_ids:
            return idx
    return None


# ---------------------------------------------------------------------------
# Sheet rewriting
# ---------------------------------------------------------------------------


def _rewrite_sheet_data(
    sheet_xml: bytes,
    columns: Sequence[str],
    rows: list[dict[str, Any]],
    date_style_id: int | None,
) -> bytes:
    """Replace <sheetData> body with header row (preserved) + new data rows."""
    open_match = re.search(rb"<sheetData[^/>]*>", sheet_xml)
    if not open_match:
        raise ValueError("sheetData element not found in sheet XML")
    body_start = open_match.end()
    body_end = sheet_xml.index(b"</sheetData>", body_start)
    body = sheet_xml[body_start:body_end]

    header_match = re.search(rb"<row\b[^>]*>.*?</row>", body, re.DOTALL)
    if not header_match:
        raise ValueError("No header row in sheetData")
    header = header_match.group(0)

    if rows:
        data = b"".join(
            _build_row(2 + i, columns, row, date_style_id) for i, row in enumerate(rows)
        )
    else:
        # Tables require at least one data row; an empty placeholder row
        # keeps Excel from flagging the file on open.
        data = _build_row(2, columns, {}, date_style_id)

    return sheet_xml[:body_start] + header + data + sheet_xml[body_end:]


def _build_row(
    row_num: int,
    columns: Sequence[str],
    values: dict[str, Any],
    date_style_id: int | None,
) -> bytes:
    cells = []
    for col_idx, col_name in enumerate(columns, start=1):
        v = values.get(col_name)
        if v is None:
            continue
        cells.append(_cell_xml(f"{_column_letter(col_idx)}{row_num}", v, date_style_id))
    return f'<row r="{row_num}">{"".join(cells)}</row>'.encode()


def _cell_xml(ref: str, value: Any, date_style_id: int | None) -> str:
    # bool must come before int -- bool is a subclass of int in Python.
    if isinstance(value, bool):
        return f'<c r="{ref}" t="b"><v>{1 if value else 0}</v></c>'
    if isinstance(value, Decimal):
        value = float(value)
    if isinstance(value, datetime):
        midnight = datetime.combine(value.date(), datetime.min.time(), value.tzinfo)
        serial = (value.date() - _EXCEL_EPOCH).days + (
            value - midnight
        ).total_seconds() / 86400
        return _numeric_cell(ref, serial, date_style_id)
    if isinstance(value, date):
        serial = (value - _EXCEL_EPOCH).days
        return _numeric_cell(ref, serial, date_style_id)
    if isinstance(value, (int, float)):
        return f'<c r="{ref}"><v>{value}</v></c>'
    # Fallback: write as inline string. xml_escape covers &, <, >.
    return f'<c r="{ref}" t="inlineStr"><is><t>{xml_escape(str(value))}</t></is></c>'


def _numeric_cell(ref: str, value: float, style_id: int | None) -> str:
    if style_id is None:
        return f'<c r="{ref}"><v>{value}</v></c>'
    return f'<c r="{ref}" s="{style_id}"><v>{value}</v></c>'


# ---------------------------------------------------------------------------
# Misc helpers
# ---------------------------------------------------------------------------


def _replace_attr(xml: bytes, element: bytes, attr: bytes, new_value: str) -> bytes:
    """Replace ``attr="..."`` on the first occurrence of ``<element ...>``."""
    pattern = rb"(<" + element + rb"\b[^>]*?\b" + attr + rb'=")[^"]*(")'
    return re.sub(pattern, rb"\g<1>" + new_value.encode() + rb"\g<2>", xml, count=1)


def _column_letter(n: int) -> str:
    """1 -> 'A', 26 -> 'Z', 27 -> 'AA', ..."""
    s = ""
    while n > 0:
        n, r = divmod(n - 1, 26)
        s = chr(65 + r) + s
    return s


def _read(zf: zipfile.ZipFile, name: str) -> bytes:
    return zf.read(name)


__all__ = ["patch_tables"]
