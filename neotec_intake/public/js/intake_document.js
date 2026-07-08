frappe.ui.form.on('Intake Document', {
  refresh(frm) {
    if (frm.is_new()) {
      frm.dashboard.set_headline(__('Save, then use Extract to read the attached file.'));
      return;
    }
    frm.add_custom_button(__('Extract'), () => {
      frappe.call({
        method: 'neotec_intake.neotec_intake.api.intake.extract',
        args: { docname: frm.doc.name }, freeze: true, freeze_message: __('Reading document…'),
      }).then((r) => { frm.reload_doc(); frappe.show_alert({ message: (r.message && r.message.message) || __('Done'), indicator: 'blue' }); });
    });
    if (['Extracted', 'Committed'].includes(frm.doc.status) && !frm.doc.created_document) {
      frm.add_custom_button(__('Create Document'), () => {
        frappe.call({
          method: 'neotec_intake.neotec_intake.api.intake.commit',
          args: { docname: frm.doc.name }, freeze: true, freeze_message: __('Creating draft…'),
        }).then((r) => {
          frm.reload_doc();
          const c = r.message && r.message.created && r.message.created[0];
          if (c) {
            const url = `/app/${frappe.router.slug(c.doctype)}/${encodeURIComponent(c.name)}`;
            frappe.msgprint({
              title: __('Draft created'), indicator: 'green',
              message: __('Created draft {0}: ', [c.doctype])
                + `<a href="${url}"><b>${frappe.utils.escape_html(c.name)}</b></a>`,
            });
          }
        });
      }).addClass('btn-primary');
    }
    if (frm.doc.created_document) {
      const url = `/app/${frappe.router.slug(frm.doc.created_doctype)}/${encodeURIComponent(frm.doc.created_document)}`;
      frm.dashboard.set_headline(
        __('Created draft {0}: ', [frm.doc.created_doctype])
        + `<a href="${url}"><b>${frappe.utils.escape_html(frm.doc.created_document)}</b></a>`
      );
      frm.add_custom_button(__('Open {0}', [frm.doc.created_doctype]), () => {
        frappe.set_route('Form', frm.doc.created_doctype, frm.doc.created_document);
      }).addClass('btn-primary');
    }
    render_preview(frm);
  },
  extracted_json(frm) { render_preview(frm); },
});

function render_preview(frm) {
  const field = frm.get_field('preview_html');
  if (!field) return;
  const w = field.$wrapper; w.empty();
  let data; try { data = JSON.parse(frm.doc.extracted_json || '{}'); } catch (e) { w.html('<div class="text-muted">' + __('Edit the JSON above to fix parsing.') + '</div>'); return; }
  const header = data.header || {}; const rows = data.rows || [];
  const esc = frappe.utils.escape_html;
  let html = '<div style="font-size:12px">';
  if (Object.keys(header).length) {
    html += '<b>' + __('Header') + '</b><table class="table table-bordered" style="margin:4px 0"><tbody>';
    for (const k in header) html += `<tr><td style="width:40%">${esc(k)}</td><td>${esc(String(header[k] ?? ''))}</td></tr>`;
    html += '</tbody></table>';
  }
  if (rows.length) {
    const cols = [...new Set(rows.flatMap((r) => Object.keys(r)))];
    html += `<b>${rows.length} ${__('line(s)')}</b><div style="overflow:auto"><table class="table table-bordered" style="margin:4px 0"><thead><tr>`
      + cols.map((c) => `<th>${esc(c)}</th>`).join('') + '</tr></thead><tbody>';
    rows.slice(0, 50).forEach((r) => { html += '<tr>' + cols.map((c) => `<td>${esc(String(r[c] ?? ''))}</td>`).join('') + '</tr>'; });
    html += '</tbody></table></div>';
    if (rows.length > 50) html += `<div class="text-muted">… ${rows.length - 50} ${__('more')}</div>`;
  }
  if (!Object.keys(header).length && !rows.length) html += '<div class="text-muted">' + __('No data yet — click Extract.') + '</div>';
  html += '</div>';
  w.html(html);
}
