from reportlab.platypus import (Image,Paragraph,Spacer,Table,TableStyle,)
from reportlab.lib.styles import (ParagraphStyle,getSampleStyleSheet,)
from reportlab.lib.enums import TA_CENTER
from reportlab.lib import colors

def add_company_header(story, company):

    styles = getSampleStyleSheet()

    title_style = ParagraphStyle(
        "CompanyTitle",
        parent=styles["Title"],
        alignment=TA_CENTER,
        fontName="Helvetica-Bold",
        fontSize=20,
        leading=22,
        spaceAfter=3,
    )

    info_style = ParagraphStyle(
        "CompanyInfo",
        parent=styles["Normal"],
        alignment=TA_CENTER,
        fontName="Helvetica",
        fontSize=11,
        leading=14,
        textColor=colors.HexColor("#444444"),
    )

    if company and company.logo:

        logo = Image(company.logo.path)

        logo.drawWidth = 55
        logo.drawHeight = 55
        logo.hAlign = "CENTER"

        story.append(logo)
        story.append(Spacer(1, 6))

    if company:

        story.append(
            Paragraph(
                f"<b>{company.name}</b>",
                title_style,
            )
        )

        if company.tagline:
            story.append(
                Paragraph(
                    company.tagline,
                    info_style,
                )
            )

        if company.address:
            story.append(
                Paragraph(
                    company.address,
                    info_style,
                )
            )

        if company.phone:
            story.append(
                Paragraph(
                    f"Phone: {company.phone}",
                    info_style,
                )
            )

    story.append(Spacer(1, 12))

    line = Table(
        [[""]],
        colWidths=[450],
    )

    line.setStyle(
        TableStyle([
            ("LINEBELOW", (0, 0), (-1, 0), 1, colors.grey),
            ("BOTTOMPADDING", (0, 0), (-1, 0), 8),
        ])
    )

    story.append(line)
    story.append(Spacer(1, 10))


def add_report_title(story, title):

    styles = getSampleStyleSheet()

    report_title = ParagraphStyle(
        "ReportTitle",
        parent=styles["Heading1"],
        alignment=TA_CENTER,
        fontName="Helvetica-Bold",
        fontSize=18,
        spaceAfter=15,
    )

    story.append(
        Paragraph(
            title,
            report_title
        )
    )

    story.append(Spacer(1, 20))


def add_report_info(story, report_info):

    info_table = Table(
        report_info,
        colWidths=[90, 250]
    )

    info_table.setStyle(TableStyle([

        ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#F2F2F2")),

        ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),

        ("GRID", (0, 0), (-1, -1), 0.25, colors.lightgrey),

        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),

        ("TOPPADDING", (0, 0), (-1, -1), 5),

    ]))

    story.append(info_table)

    story.append(Spacer(1, 20))


def add_summary_table(story, heading, summary_data,col_widths=(140, 120)):

    styles = getSampleStyleSheet()

    story.append(
        Paragraph(
            heading,
            styles["Heading2"]
        )
    )

    story.append(
        Spacer(1, 8)
    )

    summary_table = Table(summary_data,colWidths=col_widths,)

    summary_table.setStyle(TableStyle([

        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#D9EAD3")),

        ("FONTNAME", (0, 0), (-1, -1), "Helvetica-Bold"),

        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),

        ("TOPPADDING", (0, 0), (-1, -1), 6),

        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),

        ("ALIGN", (1, 0), (1, -1), "RIGHT"),

    ]))

    story.append(summary_table)

    story.append(
        Spacer(1, 10)
    )  


def style_report_table(table,row_count,header_color="#1f4e78"):

    table.setStyle(TableStyle([

        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1f4e78")),

        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),

        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),

        ("TOPPADDING", (0, 0), (-1, 0), 8),

        ("BOTTOMPADDING", (0, 0), (-1, 0), 8),

        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),

        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),

    ]))

    ("BACKGROUND",(0,0),(-1,0),colors.HexColor(header_color)),

    for row in range(1, row_count):

        if row % 2 == 0:

            table.setStyle(TableStyle([
                ("BACKGROUND", (0, row), (-1, row), colors.whitesmoke)
            ]))

        else:

            table.setStyle(TableStyle([
                ("BACKGROUND", (0, row), (-1, row), colors.beige)
            ]))              