"""Generate ten reproducible, selectable-text, three-page fictional RFP PDFs.

Only Python's standard library is used so sample creation works before pip install.
"""

from __future__ import annotations

import re
import textwrap
from pathlib import Path

from sample_data import PROPOSALS, REQUEST

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "sample_rfps"


def escape(value: str) -> str:
    value = value.encode("ascii", "replace").decode("ascii")
    return value.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def page_stream(proposal: dict, page: int) -> bytes:
    lines: list[tuple[str, int, int]] = []
    y = 750

    def add(text: str, size: int = 10, gap: int = 16, indent: int = 52) -> None:
        nonlocal y
        lines.append((text, size, y, indent))
        y -= gap

    def section(title: str, body: str) -> None:
        nonlocal y
        y -= 12
        add(title.upper(), 12, 20)
        for paragraph in body.split("\n"):
            for wrapped in textwrap.wrap(paragraph, width=94, break_long_words=False):
                add(wrapped)

    add("NORTHSTAR BOROUGH COUNCIL | RFP RESPONSE", 10, 22)
    add(proposal["name"], 20, 32)
    add(f"Submission: {proposal['date']}    Page {page} of 3", 10, 25)
    if page == 1:
        section("1. Executive summary and requirement understanding", proposal["summary"])
        section("Common procurement request", REQUEST)
        section("2. Proposed solution and technical approach", proposal["solution"])
    elif page == 2:
        section("3. Implementation timeline, team and milestones", proposal["implementation"])
        section("4. Price table and assumptions (USD)", proposal["price"])
        section("Commercial clarification", "All prices are fictional classroom values. Taxes are excluded. Only explicit inclusions in this proposal should be considered committed scope.")
    else:
        section("5. Security, compliance and privacy controls", proposal["security"])
        section("6. Support model, experience and references", proposal["support"])
        section("7. Delivery risks and gaps", proposal["risks"])
    add("Synthetic classroom proposal. No confidential supplier information.", 9, 12)
    assert y > 60, (proposal["name"], page, y)
    commands = ["BT"]
    for text, size, yy, xx in lines:
        commands.extend([f"/F1 {size} Tf", f"1 0 0 1 {xx} {yy} Tm", f"({escape(text)}) Tj"])
    commands.append("ET")
    return "\n".join(commands).encode("ascii")


def write_pdf(path: Path, proposal: dict) -> None:
    # PDF 1.4 with a standard Helvetica font and uncompressed text streams.
    objects: list[bytes] = []

    def obj(data: bytes) -> int:
        objects.append(data)
        return len(objects)

    catalog = obj(b"<< /Type /Catalog /Pages 2 0 R >>")
    pages = obj(b"")
    font = obj(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")
    page_ids = []
    for number in (1, 2, 3):
        stream = page_stream(proposal, number)
        content_id = obj(b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream")
        page_ids.append(obj(
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
            + b"/Resources << /Font << /F1 " + str(font).encode() + b" 0 R >> >> "
            + b"/Contents " + str(content_id).encode() + b" 0 R >>"
        ))
    objects[pages - 1] = b"<< /Type /Pages /Count 3 /Kids [" + b" ".join(f"{pid} 0 R".encode() for pid in page_ids) + b"] >>"
    assert catalog == 1
    data = bytearray(b"%PDF-1.4\n%Synthetic RFP\n")
    offsets = [0]
    for index, body in enumerate(objects, 1):
        offsets.append(len(data))
        data.extend(f"{index} 0 obj\n".encode() + body + b"\nendobj\n")
    start = len(data)
    data.extend(f"xref\n0 {len(offsets)}\n0000000000 65535 f \n".encode())
    for offset in offsets[1:]:
        data.extend(f"{offset:010d} 00000 n \n".encode())
    data.extend(f"trailer\n<< /Size {len(offsets)} /Root 1 0 R >>\nstartxref\n{start}\n%%EOF\n".encode())
    path.write_bytes(data)


def main() -> None:
    OUT.mkdir(exist_ok=True)
    for proposal in PROPOSALS:
        name = re.sub(r"[^a-z0-9]+", "_", proposal["name"].lower()).strip("_")
        path = OUT / f"{name}.pdf"
        write_pdf(path, proposal)
        print(path.name)


if __name__ == "__main__":
    main()
