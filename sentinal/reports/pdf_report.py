"""Small offline PDF report generator with an explicit reportlab fallback."""
from __future__ import annotations
from typing import Any, Iterable

def generate_pdf(records: Iterable[Any], *, title: str = "SENTINAL Risk Report") -> bytes:
    try:
        from reportlab.pdfgen import canvas
        from reportlab.lib.pagesizes import letter
    except ImportError as exc:
        raise RuntimeError("PDF export requires optional dependency 'reportlab'") from exc
    import io, json
    out=io.BytesIO(); c=canvas.Canvas(out,pagesize=letter); y=760
    c.setFont("Helvetica-Bold",14); c.drawString(48,y,title); y-=28; c.setFont("Helvetica",9)
    for item in records:
        d=item.model_dump() if hasattr(item,"model_dump") else ({k:getattr(item,k) for k in item.__dataclass_fields__} if hasattr(item,"__dataclass_fields__") else dict(item))
        text=json.dumps(d,default=str,sort_keys=True)
        for line in [text[i:i+105] for i in range(0,len(text),105)]:
            if y<45: c.showPage(); y=760
            c.drawString(48,y,line); y-=12
    c.save(); return out.getvalue()
