"""Deterministic reader for KSA tax invoices across vendor layouts (bilingual
Arabic/English). Extracts the header fields that are reliably present; the
supplier is identified by excluding our own company's VAT from the VAT numbers
on the document. Full line-item tables vary too much between vendors — configure
an AI model for those. Used when no AI is available."""
import re

_AMT = r'([0-9][0-9,]*\.[0-9]{2})'
_MONTHS = {"jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
           "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12}


def _num(s):
    try:
        return float(str(s).replace(",", "").strip())
    except Exception:
        return None


def looks_like_invoice(text: str) -> bool:
    if not text:
        return False
    hits = sum(bool(re.search(p, text, re.I)) for p in
               (r"Tax Invoice", r"VAT", r"Invoice", r"Total", r"فاتورة"))
    return hits >= 2


def _invoice_no(text):
    for pat in (r"Invoice\s*No\.?\s*[:\-]?\s*([A-Za-z][A-Za-z0-9\-/]{2,})",
                r"INVOICE\s*NO\.?\s*[:\-]?\s*([A-Za-z0-9][A-Za-z0-9\-/]{2,})",
                r"Invoice\s*No[^A-Za-z0-9\n]{0,3}([A-Za-z0-9][A-Za-z0-9\-/]{3,})"):
        m = re.search(pat, text, re.I)
        if m:
            val = m.group(1).strip().rstrip(".")
            if val.lower() not in ("no", "number", "sr"):
                return val
    return None


def _date(text):
    m = re.search(r"(\d{4}-\d{2}-\d{2})", text)
    if m:
        return m.group(1)
    m = re.search(r"\b(\d{1,2})/(\d{1,2})/(\d{4})\b", text)
    if m:
        d, mo, y = m.groups()
        if 1 <= int(mo) <= 12 and 1 <= int(d) <= 31:
            return f"{y}-{int(mo):02d}-{int(d):02d}"
    m = re.search(r"\b([A-Z][a-z]{2})\s+(\d{1,2}),?\s+(\d{4})\b", text)
    if m and m.group(1).lower() in _MONTHS:
        return f"{m.group(3)}-{_MONTHS[m.group(1).lower()]:02d}-{int(m.group(2)):02d}"
    return None


def _all_vats(text):
    """Ordered, de-duplicated 15-digit VAT numbers that sit near a VAT/tax label,
    each tagged seller/customer by nearby wording."""
    found, seen = [], set()
    for m in re.finditer(r"\b(\d{15})\b", text):
        v = m.group(1)
        ctx = text[max(0, m.start() - 45):m.end() + 12].lower()
        if not any(k in ctx for k in ("vat", "ضريب", "الضريبي", "tax")):
            continue
        if v in seen:
            continue
        seen.add(v)
        kind = "customer" if any(k in ctx for k in ("customer", "cust", "client", "عميل")) else "seller"
        found.append((v, kind))
    return found


_HEADER_HINT = re.compile(r"Description|Unit Price|Extended Price|\bQTY\b|Item Number|"
                          r"Price Excl|Unit/Period|Taxable Amount\b", re.I)


def _amount_for(labels, text):
    """Find a total only when the amount is on the SAME line as the label.
    Conservative by design: a blank total is safer than a wrong one, since these
    feed accounting documents. Column/box layouts (where label and value are
    separated) are left for the AI path."""
    lines = text.splitlines()
    for lab in labels:
        for line in lines:
            if _HEADER_HINT.search(line):
                continue
            if re.search(lab, line, re.I):
                nums = re.findall(_AMT, line)
                if nums:
                    return _num(nums[-1])
    return None


def parse(text: str, company_vat: str | None = None) -> dict:
    fields, rows = {}, []
    if not text:
        return {"fields": fields, "rows": rows}

    inv = _invoice_no(text)
    if inv:
        fields["bill_no"] = inv
    dt = _date(text)
    if dt:
        fields["posting_date"] = dt

    vats = _all_vats(text)
    all_v = [v for v, _ in vats]
    fields["vat_numbers"] = all_v
    sellers = [v for v, k in vats if k == "seller"]
    buyers = [v for v, k in vats if k == "customer"]
    # the supplier's VAT is whichever isn't our own company VAT
    if company_vat:
        non_self = [v for v in all_v if v != company_vat]
        if non_self:
            fields["seller_vat"] = non_self[0]
        self_v = [v for v in all_v if v == company_vat]
        if self_v:
            fields["buyer_vat"] = company_vat
    if "seller_vat" not in fields and sellers:
        fields["seller_vat"] = sellers[0]
    if "buyer_vat" not in fields and buyers:
        fields["buyer_vat"] = buyers[0]

    net = _amount_for([r"Subtotal Before VAT", r"Total Before VAT", r"Sub\s*Total",
                       r"Total\s*\(\s*Excluding VAT"], text)
    vat = _amount_for([r"Total VAT", r"VAT Amount", r"VAT\s*15\s*%"], text)
    grand = _amount_for([r"Net After VAT", r"Grand Total", r"Total Amount Due",
                         r"Total After VAT"], text)
    if net is not None:
        fields["net_total"] = net
    if vat is not None:
        fields["total_taxes_and_charges"] = vat
    if grand is not None:
        fields["grand_total"] = grand

    party = [n.strip() for n in re.findall(r"(?:Client Name|Customer Name|Name)\s+([A-Za-z][A-Za-z0-9 .,&'\-]{2,60})", text)]
    if party:
        fields["party_name"] = party[0]

    # single line-item heuristic (best-effort across layouts)
    lines = [l.rstrip() for l in text.splitlines() if l.strip()]
    for i, l in enumerate(lines):
        if re.match(r"^\d+(\.\d+)?\s", l) and len(re.findall(_AMT, l)) >= 2:
            nums = re.findall(r"([0-9][0-9,]*\.[0-9]+)", l)
            row = {"qty": _num(nums[0]) or 1}
            if len(nums) > 1:
                row["rate"] = _num(nums[1])
            desc = [lines[j].strip() for j in range(i + 1, min(i + 3, len(lines)))
                    if re.search(r"[A-Za-z]{3,}", lines[j]) and not re.search(r"Total|VAT|Amount|Stamp|Subtotal", lines[j])]
            if desc:
                row["description"] = " ".join(desc)
            rows.append(row)
            break
    return {"fields": fields, "rows": rows}
