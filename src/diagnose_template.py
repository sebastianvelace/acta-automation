import os
import re
from docxtpl import DocxTemplate

TEMPLATE_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "templates", "acta_template.docx"
)


def find_with_context(xml: str, pattern: str, ctx: int = 50):
    results = []
    for m in re.finditer(re.escape(pattern), xml):
        start = max(0, m.start() - ctx)
        end = min(len(xml), m.end() + ctx)
        snippet = xml[start:end].replace("\n", "↵")
        results.append(snippet)
    return results


def main():
    print(f"Loading: {TEMPLATE_PATH}\n")
    tpl = DocxTemplate(TEMPLATE_PATH)
    tpl.init_docx()  # trigger lazy load (docxtpl 0.20+ defers Document() to init_docx)

    # Get the preprocessed XML docxtpl hands to Jinja2
    xml = tpl.get_xml()

    print(f"Total XML length: {len(xml)} chars\n")

    tags = [
        "{% for",
        "{% endfor",
        "{%p for",
        "{%p endfor",
        "{%tr for",
        "{%tr endfor",
    ]

    for tag in tags:
        hits = find_with_context(xml, tag)
        print(f"=== '{tag}' — {len(hits)} occurrence(s) ===")
        for i, snippet in enumerate(hits, 1):
            print(f"  [{i}] ...{snippet}...")
        print()

    # Try patch_xml if available (requires src_xml argument in 0.20+)
    if hasattr(tpl, "patch_xml"):
        print("=== tpl.patch_xml() available — calling with current XML ===")
        try:
            patched = tpl.patch_xml(xml)
            print(f"Post-patch XML length: {len(patched)} chars")
        except Exception as e:
            print(f"  patch_xml error: {e}")
    else:
        print("tpl.patch_xml() not available on this docxtpl version")

    # Also dump a raw slice around 'asuntos' for manual inspection
    print("\n=== Raw XML slice around 'asuntos_tratados' ===")
    idx = xml.find("asuntos_tratados")
    if idx != -1:
        print(xml[max(0, idx - 200): idx + 300].replace("\n", "↵"))
    else:
        print("  'asuntos_tratados' not found in XML")

    print("\n=== Raw XML slice around 'objetivo' ===")
    idx = xml.find("objetivo")
    if idx != -1:
        print(xml[max(0, idx - 100): idx + 200].replace("\n", "↵"))
    else:
        print("  'objetivo' not found in XML")


if __name__ == "__main__":
    main()
