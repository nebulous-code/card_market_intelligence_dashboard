"""
Resource guards for untrusted uploaded workbooks.

``/collection/upload`` accepts a file from anyone on the internet with no
authentication, which is the correct design -- the endpoint only ever
writes to a session scoped to the caller's own cookie, so there is
nothing to protect with a key. What does need protecting is the server's
memory and database, and an `.xlsx` gives an attacker three separate
levers:

1. **Raw size.** The router reads the body into memory before anything
   else can look at it.
2. **Decompression.** An `.xlsx` is a zip archive and openpyxl expands
   it on open. Real workbooks in this project sit around a 4x ratio; a
   crafted bomb is thousands of x, so a payload small enough to pass a
   byte cap can still exhaust memory once opened.
3. **Row count.** ``collection_validator._resolve_card_id`` issues one
   database query per row, so a tall sheet is a database denial of
   service at a trivial file size. Bytes alone will not catch it.

Each lever gets its own check, and every limit is environment
overridable so it can be tightened in production without a deploy of
new code. Defaults are deliberately loose: they sit far above any
plausible collection, because a false rejection costs a real user their
upload while a generous ceiling still closes the attack.

Limits are read inside the accessor functions rather than at import
time. That is the same pattern as ``routers.collection._cookie_secure``
and it is what lets tests use ``monkeypatch.setenv`` without reloading
the module.
"""

from __future__ import annotations

import os
import zipfile
from io import BytesIO

# Measured, not guessed. Building collection workbooks of varying size
# and loading them under tracemalloc:
#
#     rows    on-wire  uncompressed  ratio   openpyxl heap  heap/uncomp
#    1,000     30,408       384,965  12.7x       3,168,416         8.2x
#    5,000    129,982     1,896,965  14.6x      15,240,910         8.0x
#   20,000    503,626     7,656,984  15.2x      61,110,816         8.0x
#
# Two things drive the numbers below. First, openpyxl's in-memory model
# costs a consistent ~8x the uncompressed XML, and ``check_row_count``
# cannot help because it runs *after* ``load_workbook`` -- so the
# uncompressed cap is the only thing standing between an upload and the
# heap. At 50 MB it would permit ~400 MB on a 512 MB instance from a
# ~3 MB upload that passed every other check: an OOM, not a 413. 8 MB
# caps openpyxl near 64 MB, which two concurrent uploads survive.
#
# Second, the compression ratio *rises* with row count (12.7x to 15.2x
# above) because repeated cell XML compresses well. A cap calibrated on
# the near-empty template would reject large-but-legitimate uploads.
#
# Headroom on the 8 MB cap: a 5,000-row collection is 1.9 MB
# uncompressed (4.2x clear), and the mock collection is 25 KB. The row
# cap trips first for anything realistic, which is the intended order --
# it produces the clearer error message.
_DEFAULT_MAX_UPLOAD_BYTES = 5 * 1024 * 1024  # 5 MB
_DEFAULT_MAX_UNCOMPRESSED_BYTES = 8 * 1024 * 1024  # 8 MB -> ~64 MB heap
_DEFAULT_MAX_COMPRESSION_RATIO = 100  # 6.6x clear of the observed 15.2x
_DEFAULT_MAX_ZIP_MEMBERS = 1_000
_DEFAULT_MAX_DATA_ROWS = 2_000


class UploadTooLarge(Exception):
    """Payload exceeded a resource limit. Router maps this to 413."""


class UploadNotReadable(Exception):
    """Payload is not a workbook we can open. Router maps this to 422."""


def _int_env(name: str, default: int) -> int:
    """Read a positive integer setting, falling back on anything odd.

    A malformed override must not take the API down at request time, so
    a non-numeric or non-positive value is treated as absent rather than
    raised. The default is always safe.
    """
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError:
        return default
    return value if value > 0 else default


def max_upload_bytes() -> int:
    return _int_env("MAX_UPLOAD_BYTES", _DEFAULT_MAX_UPLOAD_BYTES)


def max_uncompressed_bytes() -> int:
    return _int_env("MAX_UNCOMPRESSED_BYTES", _DEFAULT_MAX_UNCOMPRESSED_BYTES)


def max_compression_ratio() -> int:
    return _int_env("MAX_COMPRESSION_RATIO", _DEFAULT_MAX_COMPRESSION_RATIO)


def max_zip_members() -> int:
    return _int_env("MAX_ZIP_MEMBERS", _DEFAULT_MAX_ZIP_MEMBERS)


def max_data_rows() -> int:
    return _int_env("MAX_DATA_ROWS", _DEFAULT_MAX_DATA_ROWS)


async def read_capped(file) -> bytes:
    """Read an ``UploadFile`` within the byte cap.

    Note what this does *not* do. By the time any handler code runs,
    Starlette's multipart parser has already consumed the whole request
    body -- FastAPI awaits ``request.form()`` before it resolves
    dependencies. The body is spooled to a ``SpooledTemporaryFile``,
    which holds the first megabyte in memory and spills the rest to
    disk. So this cannot prevent a large body from being received; only
    middleware running ahead of routing could do that.

    What it does prevent is a *second* full copy of that body living in
    the process heap, and everything downstream of it -- openpyxl's
    in-memory model is the expensive part, and it never gets the chance
    to start.

    The size check comes first when the parser has supplied one, which
    rejects a large upload without reading a byte. The chunked loop is
    the fallback and the real enforcement, since ``size`` is metadata
    and the running total is ground truth.
    """
    limit = max_upload_bytes()
    too_large = UploadTooLarge(
        f"File is larger than the {limit // (1024 * 1024)} MB limit."
    )

    # getattr rather than a None check: on a real UploadFile this is
    # always populated, so an explicit `is not None` arm would be an
    # unreachable branch under the 100% branch gate.
    declared = getattr(file, "size", None)
    if declared is not None and declared > limit:
        raise too_large

    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = await file.read(64 * 1024)
        if not chunk:
            break
        total += len(chunk)
        if total > limit:
            raise too_large
        chunks.append(chunk)
    return b"".join(chunks)


def check_workbook_bytes(file_bytes: bytes) -> None:
    """Reject bombs and non-workbooks before openpyxl touches the bytes.

    Inspecting the zip central directory is cheap: ``ZipInfo.file_size``
    is metadata, so the declared uncompressed size can be summed without
    decompressing anything. A bomb is caught before a single byte is
    expanded.

    Both the absolute uncompressed total and the ratio are checked. The
    absolute cap alone would let through a bomb that is merely large but
    within budget; the ratio alone would let through a genuinely huge
    upload that happens to compress poorly.
    """
    try:
        archive = zipfile.ZipFile(BytesIO(file_bytes))
    except zipfile.BadZipFile as exc:
        raise UploadNotReadable(
            "That file is not a readable .xlsx workbook."
        ) from exc

    with archive:
        members = archive.infolist()

        member_cap = max_zip_members()
        if len(members) > member_cap:
            raise UploadTooLarge(
                f"Workbook contains {len(members)} internal parts, "
                f"above the {member_cap} limit."
            )

        uncompressed = sum(info.file_size for info in members)
        size_cap = max_uncompressed_bytes()
        if uncompressed > size_cap:
            raise UploadTooLarge(
                f"Workbook expands to {uncompressed // (1024 * 1024)} MB, "
                f"above the {size_cap // (1024 * 1024)} MB limit."
            )

        # No zero-division guard needed: empty input cannot reach this
        # point, because zipfile rejects it as BadZipFile above.
        ratio = uncompressed / len(file_bytes)
        ratio_cap = max_compression_ratio()
        if ratio > ratio_cap:
            raise UploadTooLarge(
                f"Workbook expands {ratio:.0f}x when opened, above the "
                f"{ratio_cap}x limit. This usually means the file is "
                "corrupt or malicious."
            )

        # Any zip is not an .xlsx. Without this a valid archive of
        # arbitrary files reaches openpyxl, which raises a bare KeyError
        # looking for the content-types part -- caught by nothing, so
        # the caller gets a 500. Reading namelist() is free; the central
        # directory is already parsed.
        names = archive.namelist()
        if "[Content_Types].xml" not in names or not any(
            n.startswith("xl/") for n in names
        ):
            raise UploadNotReadable(
                "That file is a zip archive but not an Excel workbook."
            )


# Above this, a reported row count is almost certainly Excel's stale
# used range rather than real data, and the message should say how to
# fix it. A genuine collection near the cap gets the plain message.
_IMPLAUSIBLE_ROW_COUNT = 100_000


def check_row_count(row_count: int) -> None:
    """Reject sheets tall enough to make the per-row query loop hurt.

    Called once the workbook is open but before validation iterates, so
    the one-query-per-row path in ``collection_validator`` is never
    entered for an oversized sheet.

    Where the cap comes from: validation issues one card lookup per row,
    and measured against Neon that costs essentially nothing to execute
    (0.04 ms) but a full network round trip to reach. So upload time is
    round trips times rows, and the ceiling that matters is the
    frontend's 15-second request timeout rather than anything about the
    database. 2,000 rows is a very large personal collection and stays
    inside that budget whenever the API and database sit in the same
    region.

    The count comes from ``sheet.max_row``, which is the sheet's *used
    range* rather than its populated rows. Excel routinely leaves a
    stale used range behind when someone clears row contents instead of
    deleting the rows, so a visibly small workbook can report a used
    range in the hundreds of thousands. Rejecting it is still correct --
    iteration really would walk every one of those rows -- but the
    message has to tell an honest user how to fix a file that looks
    perfectly fine to them.
    """
    cap = max_data_rows()
    if row_count <= cap:
        return

    message = f"Collections over {cap:,} rows are not supported at this time."
    if row_count >= _IMPLAUSIBLE_ROW_COUNT:
        message += (
            f" This workbook reports {row_count:,} rows, which usually means "
            "Excel is still counting rows you cleared rather than deleted. "
            "Select the empty rows below your data, delete the rows "
            "themselves, save, and try again."
        )
    raise UploadTooLarge(message)


__all__ = [
    "UploadNotReadable",
    "UploadTooLarge",
    "check_row_count",
    "check_workbook_bytes",
    "max_data_rows",
    "max_upload_bytes",
    "read_capped",
]
