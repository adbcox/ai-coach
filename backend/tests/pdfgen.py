"""Build a tiny but valid text PDF for tests (no copyrighted material is ever used in tests)."""

from __future__ import annotations


def make_pdf(pages: list[list[str]], title: str | None = None) -> bytes:
    objs: list[bytes] = []

    def add(b: str | bytes) -> int:
        objs.append(b if isinstance(b, bytes) else b.encode("latin-1"))
        return len(objs)

    n_pages = len(pages)
    add("<< /Type /Catalog /Pages 2 0 R >>")                                  # 1
    kids = " ".join(f"{4 + 2 * i} 0 R" for i in range(n_pages))
    add(f"<< /Type /Pages /Kids [{kids}] /Count {n_pages} >>")                # 2
    add("<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")             # 3
    for i, lines in enumerate(pages):
        page_obj = 4 + 2 * i
        content_obj = page_obj + 1
        add(f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents {content_obj} 0 R "
            f"/Resources << /Font << /F1 3 0 R >> >> >>")
        ops = ["BT", "/F1 11 Tf", "14 TL", "50 740 Td"]
        for ln in lines:
            esc = ln.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
            ops.append(f"({esc}) Tj T*")
        ops.append("ET")
        stream = "\n".join(ops)
        add(f"<< /Length {len(stream)} >>\nstream\n{stream}\nendstream")
    info = ""
    if title:
        info_obj = add(f"<< /Title ({title}) >>")
        info = f" /Info {info_obj} 0 R"
    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for i, o in enumerate(objs, 1):
        offsets.append(len(out))
        out += f"{i} 0 obj\n".encode() + o + b"\nendobj\n"
    xref = len(out)
    out += f"xref\n0 {len(objs) + 1}\n".encode() + b"0000000000 65535 f \n"
    for off in offsets:
        out += f"{off:010d} 00000 n \n".encode()
    out += f"trailer\n<< /Size {len(objs) + 1} /Root 1 0 R{info} >>\nstartxref\n{xref}\n%%EOF\n".encode()
    return bytes(out)
