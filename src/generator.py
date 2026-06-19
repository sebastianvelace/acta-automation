import os
import subprocess

from docx.oxml.ns import qn
from docxtpl import DocxTemplate

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_OUTPUT_DIR = os.path.join(BASE_DIR, "output")


def _tc_plain_text(tc) -> str:
    parts = []
    for t_elem in tc.iter(qn("w:t")):
        if t_elem.text:
            parts.append(t_elem.text)
    return "".join(parts).strip()


def _strip_trailing_empty_columns(doc) -> None:
    """
    Remove a trailing table column iff every row's last cell is empty.
    Eliminates the ghost column left by {%tr endfor %} in the template after render.
    """
    for table in doc.tables:
        rows = list(table.rows)
        if not rows:
            continue
        tcs0 = rows[0]._tr.findall(qn("w:tc"))
        n_tc = len(tcs0)
        if n_tc < 2:
            continue
        last_idx = n_tc - 1
        if not all(
            len(row._tr.findall(qn("w:tc"))) > last_idx
            and not _tc_plain_text(row._tr.findall(qn("w:tc"))[last_idx])
            for row in rows
        ):
            continue
        for row in rows:
            tcs = row._tr.findall(qn("w:tc"))
            if tcs:
                row._tr.remove(tcs[-1])
        tbl_grid = table._tbl.find(qn("w:tblGrid"))
        if tbl_grid is not None:
            grid_cols = tbl_grid.findall(qn("w:gridCol"))
            if grid_cols:
                tbl_grid.remove(grid_cols[-1])


def generate_acta(
    data: dict,
    output_name: str,
    keep_docx: bool = True,
    output_dir: str | None = None,
) -> str:
    template_path = os.path.join(BASE_DIR, "templates", "acta_template.docx")
    print(f"Template path: {template_path}")

    if not os.path.exists(template_path):
        raise FileNotFoundError(f"Template not found at {template_path}")

    if data.get("hora_final") in (None, "") and data.get("hora_fin") not in (None, ""):
        data = {**data, "hora_final": data["hora_fin"]}

    # Growfik solo aparece en actas Universal; default conservador sin marca Growfik.
    data.setdefault("encabezado_compromisos_gorila", "GORILA")

    tpl = DocxTemplate(template_path)
    print(f"Template loaded: {type(tpl)}")
    tpl.render(data, autoescape=True)
    _strip_trailing_empty_columns(tpl.docx)

    out_dir = output_dir if output_dir is not None else _OUTPUT_DIR
    os.makedirs(out_dir, exist_ok=True)

    docx_path = os.path.join(out_dir, f"{output_name}.docx")
    tpl.save(docx_path)

    subprocess.run(
        ["libreoffice", "--headless", "--convert-to", "pdf", "--outdir", out_dir, docx_path],
        check=True,
    )

    if not keep_docx:
        os.remove(docx_path)

    return os.path.join(out_dir, f"{output_name}.pdf")
