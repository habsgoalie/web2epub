import warnings
from weasyprint import HTML


# Suppress weasyprint warnings
warnings.filterwarnings("ignore", module="weasyprint")


PDF_TEMPLATE = """<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <style>
        body {{
            font-family: Georgia, serif;
            font-size: 14pt;
            line-height: 1.6;
            max-width: 600px;
            margin: 0 auto;
            padding: 20px;
            color: #222;
        }}
        h1 {{ font-size: 20pt; margin-bottom: 0.3em; }}
        .source {{ color: #666; font-size: 10pt; margin-bottom: 2em; }}
        img {{ max-width: 100%; height: auto; }}
        a {{ color: #222; }}
        pre, code {{ font-size: 11pt; overflow-wrap: break-word; }}
    </style>
</head>
<body>
    <h1>{title}</h1>
    <p class="source">{url}</p>
    {content}
</body>
</html>
"""


def generate_pdf(title: str, content: str, url: str) -> bytes:
    """
    Convert extracted article HTML into a clean, readable PDF.
    
    Args:
        title: Article title
        content: Clean HTML content (from readability)
        url: Original source URL
    
    Returns:
        PDF as bytes
    """
    html_string = PDF_TEMPLATE.format(
        title=title,
        content=content,
        url=url
    )
    
    html = HTML(string=html_string)
    pdf_bytes = html.write_pdf()
    
    return pdf_bytes
