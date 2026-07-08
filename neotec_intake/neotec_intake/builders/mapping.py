"""Map an extracted payload onto target fields using the profile's Field Map.
With no map, keys pass through unchanged (good for AI output that already uses
the target fieldnames)."""
from frappe.utils import flt, getdate


def _transform(val, kind):
    if val in (None, ""):
        return val
    try:
        if kind == "number":
            return flt(str(val).replace(",", "").replace("SAR", "").strip())
        if kind == "date":
            return str(getdate(val))
        if kind == "upper":
            return str(val).upper()
        if kind == "lower":
            return str(val).lower()
        if kind == "strip":
            return str(val).strip()
    except Exception:
        return val
    return val


def apply_mapping(payload: dict, profile) -> dict:
    fmaps = profile.get("field_map") or []
    if not fmaps:
        return {"header": payload.get("fields", {}) or {},
                "rows": payload.get("rows", []) or []}
    header, row_maps = {}, []
    for m in fmaps:
        if m.scope == "header":
            v = (payload.get("fields", {}) or {}).get(m.source_key)
            if v in (None, "") and m.default_value not in (None, ""):
                v = m.default_value
            header[m.target_field] = _transform(v, m.transform)
        else:
            row_maps.append(m)
    rows = []
    for r in (payload.get("rows", []) or []):
        rec = {}
        for m in row_maps:
            v = r.get(m.source_key)
            if v in (None, "") and m.default_value not in (None, ""):
                v = m.default_value
            rec[m.target_field] = _transform(v, m.transform)
        if any(str(v) != "" for v in rec.values()):
            rows.append(rec)
    return {"header": header, "rows": rows}
