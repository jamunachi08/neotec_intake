# Neotec DocIntake

Read **images, PDFs, Excel and CSV** and turn them into **draft ERPNext documents**
— Purchase Invoice, Purchase Order, Journal Entry, Lead, or any DocType — across
modules. Generalises the bank-slip reader pattern into a configurable, installable
framework.

## How it works
1. **Intake Profile** — defines a target DocType, a builder, a source type, and a
   **Field Map** (source column / JSON key → target field, header or row scope).
2. **Intake Document** — attach a file, pick a profile, click **Extract** (reads
   the file), review the parsed JSON / preview, then **Create Document** (inserts
   a *draft* for a human to check and submit). The tool proposes; a person commits.

## Extraction
- **Excel / CSV** — parsed deterministically (header auto-detected). No AI needed.
- **PDF** — text pulled (pdfplumber → pdfminer → PyPDF2); optionally structured by
  the configured model.
- **Image** — read by a vision model. With local **Ollama** (default) documents
  never leave the site (PDPL / data-sovereignty). An OpenAI-compatible endpoint is
  also supported. Optional local OCR (pytesseract) can run first.

Configure the model in **Intake Settings**.

## Builders (extensible)
`purchase_invoice`, `purchase_order`, `journal_entry`, `lead`, and `generic` (sets
mapped header fields + appends a child table). `auto` picks by target DocType.
Add more in `builders/core.py`.

## Install
```bash
bench get-app neotec_intake <repo-url>
bench --site <site> install-app neotec_intake
bench --site <site> migrate
```
Installs four starter profiles and default Intake Settings.

## Notes
- Created documents are always **drafts** (docstatus 0).
- Optional Python deps for richer PDF/OCR: `pdfplumber`, `pdfminer.six`, `pytesseract` + Pillow.

## v0.1.1
- PDF text now also read via **pypdf** (bundled with Frappe v15), fixing
  "no selectable text" on text PDFs.
- Built-in **bilingual (Arabic/English) tax-invoice reader** — extracts invoice
  number, dates, totals, VAT numbers and the line item with **no AI**, used
  automatically when no model is configured. AI (Ollama/OpenAI-compatible) still
  takes precedence when available and handles arbitrary layouts.
- Purchase Invoice builder matches the supplier by the seller's VAT (tax_id) when
  no supplier is mapped.

## v0.2.0 — multi-vendor invoice reading
- **Supplier identified by excluding our own company's VAT**: the supplier is the
  VAT number on the document that isn't the buyer's (Company.tax_id), then matched
  to a Supplier by tax_id. Works across vendor layouts even when the seller VAT
  isn't clearly labelled.
- Broader invoice-number and date patterns (ISO, DD/MM/YYYY, "Mon DD, YYYY").
- Totals read **same-line only** — correct when present, left blank otherwise
  (a blank total is safer than a wrong one in accounting). Boxed/column layouts
  where labels and values are separated are best handled by the AI path.
- For full line-item tables on arbitrary layouts, configure an AI model in Intake
  Settings; the deterministic reader reliably gives supplier, invoice no and date.
