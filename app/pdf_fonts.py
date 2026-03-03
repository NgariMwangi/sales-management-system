"""PDF font registration for Montserrat. Use regular/medium/bold where appropriate."""
import os

# Mutable so register_pdf_fonts can update after loading TTF files
_fonts = {'regular': 'Helvetica', 'bold': 'Helvetica-Bold', 'medium': 'Helvetica'}
_registered = False


def register_pdf_fonts(static_folder):
    """Register Montserrat from static/fonts/ if present. Safe to call multiple times."""
    global _registered
    if _registered:
        return
    try:
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.ttfonts import TTFont
    except ImportError:
        return
    fonts_dir = os.path.join(os.path.abspath(static_folder), 'fonts')
    if not os.path.isdir(fonts_dir):
        return
    reg = os.path.join(fonts_dir, 'Montserrat-Regular.ttf')
    bold = os.path.join(fonts_dir, 'Montserrat-Bold.ttf')
    medium = os.path.join(fonts_dir, 'Montserrat-Medium.ttf')
    try:
        if os.path.isfile(reg):
            pdfmetrics.registerFont(TTFont('Montserrat', reg))
            _fonts['regular'] = 'Montserrat'
        if os.path.isfile(bold):
            pdfmetrics.registerFont(TTFont('Montserrat-Bold', bold))
            _fonts['bold'] = 'Montserrat-Bold'
        if os.path.isfile(medium):
            pdfmetrics.registerFont(TTFont('Montserrat-Medium', medium))
            _fonts['medium'] = 'Montserrat-Medium'
        _registered = True
    except Exception:
        pass


def get_pdf_fonts():
    """Return dict of font names: regular, bold, medium. Call after register_pdf_fonts(static_folder)."""
    return _fonts
