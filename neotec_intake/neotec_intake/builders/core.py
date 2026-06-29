"""Builder registry — turn mapped data into DRAFT ERPNext documents.

Everything is inserted as a draft (docstatus 0); a person reviews and submits.
This mirrors the GRC pattern: the tool proposes, a human commits.
"""
import frappe
from frappe.utils import flt, nowdate


def _pick(profile) -> str:
    b = profile.builder or "auto"
    if b != "auto":
        return b
    return {
        "purchase invoice": "purchase_invoice",
        "purchase order": "purchase_order",
        "journal entry": "journal_entry",
        "lead": "lead",
    }.get((profile.target_doctype or "").lower(), "generic")


def build(profile, mapped: dict, extra_opts: dict | None = None) -> list:
    opts = frappe.parse_json(profile.options) if profile.get("options") else {}
    opts = {**(opts or {}), **(extra_opts or {})}
    fn = {
        "generic": _generic, "purchase_invoice": _purchase_invoice,
        "purchase_order": _purchase_order, "journal_entry": _journal_entry, "lead": _lead,
    }[_pick(profile)]
    return fn(profile, mapped, opts)


def _company(profile, opts):
    return (profile.get("default_company") or opts.get("company")
            or frappe.defaults.get_user_default("Company"))


def _expense_account(company, opts):
    """Best-effort default expense account so a draft Purchase Invoice passes
    ERPNext's item validation (which runs even on draft)."""
    acc = opts.get("expense_account")
    if acc:
        return acc
    try:
        acc = frappe.get_cached_value("Company", company, "default_expense_account")
        if acc:
            return acc
    except Exception:
        pass
    for nm in ("Cost of Goods Sold", "Expenses", "Indirect Expenses"):
        a = frappe.db.get_value("Account", {"company": company, "is_group": 0,
                                            "account_name": ["like", f"%{nm}%"]}, "name")
        if a:
            return a
    return None


def _generic(profile, mapped, opts):
    doc = frappe.new_doc(profile.target_doctype)
    for k, v in (mapped["header"] or {}).items():
        if v not in (None, "") and doc.meta.has_field(k):
            doc.set(k, v)
    ctf = profile.get("child_table_field")
    if ctf and mapped["rows"] and doc.meta.has_field(ctf):
        for r in mapped["rows"]:
            doc.append(ctf, {k: v for k, v in r.items() if v not in (None, "")})
    doc.insert(ignore_permissions=False)
    return [{"doctype": doc.doctype, "name": doc.name}]


def _match_supplier(h, opts, company):
    """For a Purchase Invoice the supplier is the SELLER. Resolve from explicit
    option/field, else by matching a Supplier whose tax_id is a VAT on the
    document other than our own company's VAT (the buyer), else by seller name."""
    s = h.get("supplier") or opts.get("supplier")
    if s:
        return s
    company_vat = None
    try:
        company_vat = frappe.db.get_value("Company", company, "tax_id")
    except Exception:
        pass
    candidates = [v for v in (h.get("vat_numbers") or []) if v and v != company_vat]
    if not candidates and h.get("seller_vat"):
        candidates = [h["seller_vat"]]
    for v in candidates:
        m = frappe.db.get_value("Supplier", {"tax_id": v}, "name")
        if m:
            return m
    if h.get("seller_name"):
        m = (frappe.db.get_value("Supplier", {"supplier_name": h["seller_name"]}, "name")
             or frappe.db.get_value("Supplier", {"name": h["seller_name"]}, "name"))
        if m:
            return m
    return None


def _purchase_invoice(profile, mapped, opts):
    h = mapped["header"]
    company = h.get("company") or _company(profile, opts)
    doc = frappe.new_doc("Purchase Invoice")
    doc.company = company
    doc.supplier = _match_supplier(h, opts, company)
    if not doc.supplier:
        frappe.throw("Could not match a Supplier from the seller's VAT or name. "
                     "Set the Supplier on the Intake Document, or in the profile's Options.")
    if h.get("bill_no"):
        doc.bill_no = h["bill_no"]
    if h.get("posting_date"):
        doc.set_posting_time = 1
        doc.posting_date = h["posting_date"]
    exp = _expense_account(company, opts)
    item_code = opts.get("item_code")
    cost_center = opts.get("cost_center")
    for r in (mapped["rows"] or []):
        row = {
            "item_code": r.get("item_code") or item_code,
            "item_name": (r.get("item_name") or r.get("description") or "Item")[:140],
            "description": r.get("description") or r.get("item_name") or "Item",
            "qty": flt(r.get("qty") or 1),
            "rate": flt(r.get("rate") or r.get("amount") or 0),
            "expense_account": r.get("expense_account") or opts.get("expense_account") or exp,
        }
        if cost_center:
            row["cost_center"] = cost_center
        doc.append("items", row)
    if not doc.get("items"):
        row = {
            "item_code": item_code,
            "item_name": "Document total", "description": h.get("remarks") or "Imported document",
            "qty": 1, "rate": flt(h.get("net_total") or h.get("grand_total") or h.get("amount") or 0),
            "expense_account": opts.get("expense_account") or exp}
        if cost_center:
            row["cost_center"] = cost_center
        doc.append("items", row)
    doc.insert(ignore_permissions=False)
    return [{"doctype": "Purchase Invoice", "name": doc.name}]


def _purchase_order(profile, mapped, opts):
    h = mapped["header"]
    doc = frappe.new_doc("Purchase Order")
    doc.company = h.get("company") or _company(profile, opts)
    doc.supplier = _match_supplier(h, opts, doc.company)
    if not doc.supplier:
        frappe.throw("Could not match a Supplier from the seller's VAT or name. "
                     "Set the Supplier on the Intake Document, or in the profile's Options.")
    doc.transaction_date = h.get("transaction_date") or h.get("posting_date") or nowdate()
    sched = h.get("schedule_date") or doc.transaction_date
    item_code = opts.get("item_code")
    cost_center = opts.get("cost_center")
    for r in (mapped["rows"] or []):
        row = {
            "item_code": r.get("item_code") or item_code,
            "item_name": r.get("item_name") or r.get("description") or "Item",
            "description": r.get("description") or r.get("item_name") or "Item",
            "qty": flt(r.get("qty") or 1),
            "rate": flt(r.get("rate") or 0),
            "schedule_date": r.get("schedule_date") or sched,
        }
        if cost_center:
            row["cost_center"] = cost_center
        doc.append("items", row)
    doc.insert(ignore_permissions=False)
    return [{"doctype": "Purchase Order", "name": doc.name}]


def _journal_entry(profile, mapped, opts):
    h = mapped["header"]
    doc = frappe.new_doc("Journal Entry")
    doc.company = h.get("company") or _company(profile, opts)
    doc.posting_date = h.get("posting_date") or nowdate()
    doc.voucher_type = h.get("voucher_type") or "Journal Entry"
    if h.get("user_remark"):
        doc.user_remark = h["user_remark"]
    for r in (mapped["rows"] or []):
        if not r.get("account"):
            continue
        line = {
            "account": r.get("account"),
            "debit_in_account_currency": flt(r.get("debit") or 0),
            "credit_in_account_currency": flt(r.get("credit") or 0),
            "cost_center": r.get("cost_center") or opts.get("cost_center"),
        }
        if r.get("party_type"):
            line["party_type"] = r["party_type"]
            line["party"] = r.get("party")
        doc.append("accounts", line)
    doc.insert(ignore_permissions=False)
    return [{"doctype": "Journal Entry", "name": doc.name}]


def _lead(profile, mapped, opts):
    created = []
    recs = mapped["rows"] or [mapped["header"]]
    for r in recs:
        src = {**(mapped["header"] or {}), **(r or {})}
        doc = frappe.new_doc("Lead")
        doc.lead_name = src.get("lead_name") or src.get("full_name") or src.get("name") or "Unnamed Lead"
        for f in ("email_id", "mobile_no", "phone", "company_name", "source", "status", "territory", "no_of_employees"):
            if src.get(f):
                doc.set(f, src[f])
        if not doc.get("email_id") and src.get("email"):
            doc.email_id = src["email"]
        if not doc.get("mobile_no") and src.get("mobile"):
            doc.mobile_no = src["mobile"]
        if not doc.get("company_name") and src.get("company"):
            doc.company_name = src["company"]
        doc.insert(ignore_permissions=False)
        created.append({"doctype": "Lead", "name": doc.name})
    return created
