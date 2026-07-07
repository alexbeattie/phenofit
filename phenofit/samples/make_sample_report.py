"""Generate a realistic (but fictional) genetic diagnostic lab report PDF.

A test fixture for the PDF drag-and-drop: it contains a clinical history
(phenotypes) and a results table (reported variants) that the AI edge should be
able to read back into the tool. The case is deliberately a *dual diagnosis* —
SCN1A explains the neuro features, FBN1 explains the connective-tissue ones — so
the review has something interesting to say.

    python -m phenofit.samples.make_sample_report   # writes sample_lab_report.pdf

Everything here is invented. Not a real patient, not real medical advice.
"""

from __future__ import annotations

from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

OUT = Path(__file__).parent / "sample_lab_report.pdf"

NAVY = colors.HexColor("#1f3a5f")
GREY = colors.HexColor("#666666")
LINE = colors.HexColor("#cccccc")


def build() -> None:
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle("Lab", parent=styles["Title"], fontSize=17, textColor=NAVY, spaceAfter=2))
    styles.add(ParagraphStyle("LabSub", parent=styles["Normal"], fontSize=8.5, textColor=GREY))
    styles.add(ParagraphStyle("H", parent=styles["Heading2"], fontSize=11, textColor=NAVY,
                              spaceBefore=14, spaceAfter=4))
    styles.add(ParagraphStyle("Body", parent=styles["Normal"], fontSize=9.5, leading=13))
    styles.add(ParagraphStyle("Small", parent=styles["Normal"], fontSize=8, textColor=GREY, leading=10))

    doc = SimpleDocTemplate(
        str(OUT), pagesize=LETTER,
        topMargin=0.7 * inch, bottomMargin=0.7 * inch,
        leftMargin=0.8 * inch, rightMargin=0.8 * inch,
        title="Genetic Test Report", author="Meridian Genetics Laboratory",
    )
    story = []

    story.append(Paragraph("Meridian Genetics Laboratory", styles["Lab"]))
    story.append(Paragraph(
        "1400 Genome Way, Suite 300, Cambridge, MA 02142 &nbsp;|&nbsp; CLIA #99D0000000 &nbsp;|&nbsp; "
        "Lab Director: Priya N. Rao, MD, PhD, FACMG", styles["LabSub"]))
    story.append(Spacer(1, 6))
    story.append(Table([[""]], colWidths=[6.9 * inch],
                       style=TableStyle([("LINEBELOW", (0, 0), (-1, -1), 1, NAVY)])))
    story.append(Paragraph("MOLECULAR GENETICS — DIAGNOSTIC EXOME, TARGETED ANALYSIS", styles["H"]))

    demo = [
        ["Patient:", "Doe, Jordan (fictional)", "Accession:", "MG-2026-004821"],
        ["DOB / Sex:", "2021-08-14 / M", "Specimen:", "Peripheral blood (EDTA)"],
        ["MRN:", "FIC-0099231", "Collected:", "2026-05-02"],
        ["Ordering provider:", "S. Nakamura, MD (Child Neurology)", "Reported:", "2026-05-29"],
    ]
    story.append(Table(
        demo, colWidths=[1.15 * inch, 2.4 * inch, 1.0 * inch, 2.35 * inch],
        style=TableStyle([
            ("FONT", (0, 0), (-1, -1), "Helvetica", 8.5),
            ("FONT", (0, 0), (0, -1), "Helvetica-Bold", 8.5),
            ("FONT", (2, 0), (2, -1), "Helvetica-Bold", 8.5),
            ("TEXTCOLOR", (0, 0), (0, -1), GREY),
            ("TEXTCOLOR", (2, 0), (2, -1), GREY),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ("TOPPADDING", (0, 0), (-1, -1), 3),
        ])))

    story.append(Paragraph("CLINICAL HISTORY", styles["H"]))
    story.append(Paragraph(
        "4-year-old boy referred for genetic evaluation of a complex neurodevelopmental and "
        "connective-tissue presentation. History of recurrent febrile and afebrile seizures with "
        "onset at 6 months of age, now with global developmental delay and gait ataxia. On "
        "ophthalmologic exam, bilateral ectopia lentis (lens dislocation) was noted. Echocardiogram "
        "demonstrated dilatation of the aortic root. Tall stature with arachnodactyly. No reported "
        "family history of sudden cardiac death. Testing requested to identify a molecular cause.",
        styles["Body"]))

    story.append(Paragraph("RESULTS — REPORTED VARIANTS", styles["H"]))
    header = ["Gene", "Variant (cDNA)", "Protein", "Zygosity", "Inheritance", "Classification"]
    rows = [
        ["SCN1A", "c.3637C>T", "p.(Arg1213Ter)", "Heterozygous", "de novo", "Pathogenic"],
        ["FBN1", "c.4082G>A", "p.(Cys1361Tyr)", "Heterozygous", "AD", "Likely pathogenic"],
        ["MYH7", "c.1063G>A", "p.(Ala355Thr)", "Heterozygous", "AD", "Uncertain significance"],
    ]
    table = Table([header] + rows, colWidths=[0.7 * inch, 1.15 * inch, 1.25 * inch,
                                              1.15 * inch, 1.05 * inch, 1.6 * inch])
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), NAVY),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONT", (0, 0), (-1, 0), "Helvetica-Bold", 8.5),
        ("FONT", (0, 1), (-1, -1), "Helvetica", 8.5),
        ("FONT", (0, 1), (0, -1), "Helvetica-Bold", 8.5),
        ("GRID", (0, 0), (-1, -1), 0.5, LINE),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f4f6fa")]),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    story.append(table)

    story.append(Paragraph("INTERPRETATION", styles["H"]))
    story.append(Paragraph(
        "<b>SCN1A</b> c.3637C&gt;T (p.Arg1213Ter) is a nonsense variant classified as "
        "<b>Pathogenic</b>. Loss-of-function variants in SCN1A cause Dravet syndrome (developmental "
        "and epileptic encephalopathy), consistent with this patient's early-onset seizures, "
        "developmental delay, and ataxia.",
        styles["Body"]))
    story.append(Spacer(1, 4))
    story.append(Paragraph(
        "<b>FBN1</b> c.4082G&gt;A (p.Cys1361Tyr) is a missense variant affecting a conserved "
        "cysteine and is classified as <b>Likely pathogenic</b>. FBN1 variants cause Marfan "
        "syndrome; the patient's ectopia lentis and aortic root dilatation are characteristic and "
        "are not explained by the SCN1A finding.",
        styles["Body"]))
    story.append(Spacer(1, 4))
    story.append(Paragraph(
        "<b>MYH7</b> c.1063G&gt;A (p.Ala355Thr) is classified as a <b>variant of uncertain "
        "significance</b>. Its clinical relevance is unknown and it should not be used for "
        "medical management at this time.",
        styles["Body"]))

    story.append(Spacer(1, 16))
    story.append(Paragraph(
        "FICTIONAL SAMPLE — generated for software testing only. Not a real patient and not a real "
        "clinical report. Variant classifications shown here are illustrative.",
        styles["Small"]))

    doc.build(story)
    print(f"wrote {OUT} ({OUT.stat().st_size} bytes)")


if __name__ == "__main__":
    build()
