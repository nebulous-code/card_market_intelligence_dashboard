"""Unit tests for ``services.upload_guard``.

These cover the guard functions directly. The router-level behaviour --
that an oversized or unreadable upload comes back as 413/422 rather than
a 500 -- is covered in ``test_routers_collection.py``.

Archives are built in memory so each failure mode can be provoked in
isolation, including a genuine (small) decompression bomb.
"""

import asyncio
import zipfile
from io import BytesIO

import pytest

from services.upload_guard import (
    UploadNotReadable,
    UploadTooLarge,
    check_row_count,
    check_workbook_bytes,
    max_data_rows,
    max_upload_bytes,
    read_capped,
)


def _zip_bytes(members: dict[str, bytes], compress=zipfile.ZIP_DEFLATED) -> bytes:
    """A bare zip. Use for testing the archive-level checks."""
    buf = BytesIO()
    with zipfile.ZipFile(buf, "w", compress) as z:
        for name, data in members.items():
            z.writestr(name, data)
    return buf.getvalue()


def _xlsx_bytes(members: dict[str, bytes], compress=zipfile.ZIP_DEFLATED) -> bytes:
    """A zip carrying the OOXML skeleton, so it reaches the size and
    ratio checks instead of stopping at the "not a workbook" check."""
    skeleton = {"[Content_Types].xml": b"<Types/>", "xl/workbook.xml": b"<w/>"}
    return _zip_bytes({**skeleton, **members}, compress)


class _FakeUpload:
    """Minimal stand-in for starlette's UploadFile.

    ``size`` defaults to None so the chunked path is the one under test;
    the fast path is exercised by passing it explicitly.
    """

    def __init__(self, data: bytes, size: int | None = None):
        self._stream = BytesIO(data)
        self.size = size

    async def read(self, size: int = -1) -> bytes:
        return self._stream.read(size)


# ---------------------------------------------------------------------------
# Limit configuration
# ---------------------------------------------------------------------------


def test_limits_fall_back_to_defaults_when_unset(monkeypatch):
    monkeypatch.delenv("MAX_UPLOAD_BYTES", raising=False)
    assert max_upload_bytes() == 5 * 1024 * 1024


def test_limits_are_environment_overridable(monkeypatch):
    monkeypatch.setenv("MAX_UPLOAD_BYTES", "1024")
    assert max_upload_bytes() == 1024


@pytest.mark.parametrize("bad", ["", "   ", "not-a-number", "0", "-5"])
def test_malformed_limit_falls_back_rather_than_raising(monkeypatch, bad):
    """A typo in an env var must not take the API down at request time,
    and must never widen a limit to zero or negative."""
    monkeypatch.setenv("MAX_DATA_ROWS", bad)
    assert max_data_rows() == 2_000


# ---------------------------------------------------------------------------
# read_capped
# ---------------------------------------------------------------------------


def test_read_capped_returns_whole_file_under_limit():
    payload = b"x" * 5_000
    assert asyncio.run(read_capped(_FakeUpload(payload))) == payload


def test_read_capped_rejects_oversized_upload(monkeypatch):
    monkeypatch.setenv("MAX_UPLOAD_BYTES", str(1024 * 1024))
    with pytest.raises(UploadTooLarge, match="larger than"):
        asyncio.run(read_capped(_FakeUpload(b"x" * (2 * 1024 * 1024))))


def test_read_capped_handles_empty_body():
    assert asyncio.run(read_capped(_FakeUpload(b""))) == b""


def test_read_capped_rejects_on_declared_size_without_reading(monkeypatch):
    """The parser populates ``size``, so an obviously oversized upload
    can be rejected without pulling a single chunk. The body here is
    empty -- if the fast path did not fire, the read loop would return
    b"" and the call would succeed."""
    monkeypatch.setenv("MAX_UPLOAD_BYTES", "1024")
    with pytest.raises(UploadTooLarge):
        asyncio.run(read_capped(_FakeUpload(b"", size=99_999)))


def test_read_capped_falls_back_to_chunking_when_size_is_absent(monkeypatch):
    """Size is metadata, not ground truth. A client-controlled or absent
    value must not be the only thing enforcing the cap."""
    monkeypatch.setenv("MAX_UPLOAD_BYTES", "1024")
    with pytest.raises(UploadTooLarge):
        asyncio.run(read_capped(_FakeUpload(b"x" * 5000, size=None)))


# ---------------------------------------------------------------------------
# check_workbook_bytes
# ---------------------------------------------------------------------------


def test_accepts_an_ordinary_archive():
    check_workbook_bytes(_xlsx_bytes({"xl/worksheets/sheet1.xml": b"<sheet/>"}))


def test_rejects_a_payload_that_is_not_a_zip():
    """An .xlsx is a zip. Anything else would raise BadZipFile deep in
    openpyxl and surface as a 500 with a stack trace."""
    with pytest.raises(UploadNotReadable, match="not a readable"):
        check_workbook_bytes(b"this is a plain text file, not a workbook")


def test_rejects_a_valid_zip_that_is_not_a_workbook():
    """Any zip is not an .xlsx. Without the skeleton check this reaches
    openpyxl, which raises a bare KeyError hunting for the content-types
    part -- caught by nothing, so the caller gets a 500."""
    payload = _zip_bytes({"readme.txt": b"hello", "data/blob.bin": b"\0" * 100})
    with pytest.raises(UploadNotReadable, match="not an Excel workbook"):
        check_workbook_bytes(payload)


def test_accepts_an_archive_with_the_ooxml_skeleton():
    check_workbook_bytes(
        _zip_bytes({"[Content_Types].xml": b"<Types/>", "xl/workbook.xml": b"<w/>"})
    )


def test_rejects_a_decompression_bomb():
    """A highly compressible payload: small on the wire, huge on open.

    This is the case a byte cap alone cannot catch -- the archive is a
    few KB but declares megabytes of content.
    """
    bomb = _xlsx_bytes({"xl/sheet1.xml": b"\0" * (20 * 1024 * 1024)})
    assert len(bomb) < 100 * 1024, "test bomb should be small on the wire"
    with pytest.raises(UploadTooLarge):
        check_workbook_bytes(bomb)


def test_rejects_on_absolute_uncompressed_size(monkeypatch):
    """Ratio and absolute size are separate gates: this archive is well
    under the ratio cap but still expands past the byte budget."""
    monkeypatch.setenv("MAX_UNCOMPRESSED_BYTES", "1024")
    monkeypatch.setenv("MAX_COMPRESSION_RATIO", "1000000")
    payload = _xlsx_bytes({"a.xml": b"abcdefgh" * 500}, compress=zipfile.ZIP_STORED)
    with pytest.raises(UploadTooLarge, match="expands to"):
        check_workbook_bytes(payload)


def test_rejects_on_compression_ratio(monkeypatch):
    """And the reverse: within the absolute budget, but implausibly
    compressible."""
    monkeypatch.setenv("MAX_UNCOMPRESSED_BYTES", str(500 * 1024 * 1024))
    monkeypatch.setenv("MAX_COMPRESSION_RATIO", "10")
    with pytest.raises(UploadTooLarge, match="expands"):
        check_workbook_bytes(_xlsx_bytes({"a.xml": b"\0" * (5 * 1024 * 1024)}))


def test_rejects_too_many_zip_members(monkeypatch):
    """A zip of many tiny entries is its own denial of service -- small
    on disk, expensive to walk."""
    monkeypatch.setenv("MAX_ZIP_MEMBERS", "5")
    payload = _xlsx_bytes({f"part{i}.xml": b"<x/>" for i in range(20)})
    with pytest.raises(UploadTooLarge, match="internal parts"):
        check_workbook_bytes(payload)


def test_empty_payload_is_not_a_zip():
    """Zero bytes reaches the BadZipFile path, so the ratio division is
    never asked to divide by zero."""
    with pytest.raises(UploadNotReadable):
        check_workbook_bytes(b"")


def test_archive_of_empty_members_has_ratio_zero():
    """An uncompressed total of 0 gives a ratio of 0, which is under any
    cap and must not raise. The divisor is the file length, which is
    always non-zero here -- a zip cannot be smaller than its
    end-of-central-directory record."""
    check_workbook_bytes(_xlsx_bytes({"empty.xml": b""}))


# ---------------------------------------------------------------------------
# check_row_count
# ---------------------------------------------------------------------------


def test_row_count_within_limit_passes():
    check_row_count(500)


def test_row_count_at_the_limit_passes(monkeypatch):
    """The cap is inclusive -- a sheet exactly at the limit is allowed,
    so the documented number means what it says."""
    monkeypatch.setenv("MAX_DATA_ROWS", "100")
    check_row_count(100)


def test_row_count_above_limit_rejected(monkeypatch):
    monkeypatch.setenv("MAX_DATA_ROWS", "100")
    with pytest.raises(UploadTooLarge, match="Collections over 100 rows"):
        check_row_count(101)


def test_plausible_overage_gets_the_plain_message(monkeypatch):
    """Someone with a genuinely large collection should not be told to
    go delete empty rows they do not have."""
    monkeypatch.setenv("MAX_DATA_ROWS", "2000")
    with pytest.raises(UploadTooLarge) as exc:
        check_row_count(2_500)
    assert "cleared rather than deleted" not in str(exc.value)


def test_implausible_row_count_explains_the_stale_used_range(monkeypatch):
    """A million-row used range is Excel bookkeeping, not data. Without
    this hint the user sees a limit they have no idea how they hit."""
    monkeypatch.setenv("MAX_DATA_ROWS", "2000")
    with pytest.raises(UploadTooLarge) as exc:
        check_row_count(1_048_576)
    assert "cleared rather than deleted" in str(exc.value)
