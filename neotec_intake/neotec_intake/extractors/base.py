"""Source detection + dispatch to the right extractor."""
import os
import frappe
from . import excel, pdf, image


def detect_type(filename: str) -> str:
    ext = (os.path.splitext(filename or "")[1] or "").lower().lstrip(".")
    if ext in ("xlsx", "xlsm", "xls"):
        return "excel"
    if ext in ("csv", "tsv"):
        return "csv"
    if ext == "pdf":
        return "pdf"
    if ext in ("png", "jpg", "jpeg", "webp", "gif", "bmp", "tiff"):
        return "image"
    return "unknown"


def _file_content(file_url: str) -> tuple[bytes, str]:
    fdoc = frappe.get_doc("File", {"file_url": file_url})
    content = fdoc.get_content()
    if isinstance(content, str):
        content = content.encode("utf-8")
    return content, (fdoc.file_name or file_url)


def run(file_url: str, profile) -> dict:
    content, fname = _file_content(file_url)
    stype = (profile.source_type or "auto")
    if stype == "auto":
        stype = detect_type(fname)
    settings = frappe.get_single("Intake Settings")
    company = profile.get("default_company")
    company_vat = None
    if company:
        try:
            company_vat = frappe.db.get_value("Company", company, "tax_id")
        except Exception:
            company_vat = None
    if stype == "excel":
        p = excel.extract_xlsx(content, sheet=profile.get("sheet") or "",
                               header_row=int(profile.get("header_row") or 0))
    elif stype == "csv":
        p = excel.extract_csv(content, header_row=int(profile.get("header_row") or 0))
    elif stype == "pdf":
        p = pdf.extract(content, profile.target_doctype, profile.get("child_table_field") or "",
                        max_pages=int(settings.get("max_pages") or 10), company_vat=company_vat)
    elif stype == "image":
        p = image.extract(content, profile.target_doctype, profile.get("child_table_field") or "",
                          ocr_enabled=bool(settings.get("ocr_enabled")), company_vat=company_vat)
    else:
        frappe.throw(f"Unsupported file type for '{fname}'. Use Excel, CSV, PDF, or an image.")
    p["source_type"] = stype
    return p
