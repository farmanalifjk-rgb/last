"""QR rendering for the FBR tracking number printed on an invoice.

The module matrix is produced by reportlab's QR encoder and painted with
Pillow, both of which the project already depends on.
"""
from io import BytesIO

from PIL import Image
from reportlab.graphics.barcode import qr

QUIET_ZONE_MODULES = 4


def render_qr_png(data, *, module_size=6, quiet_zone=QUIET_ZONE_MODULES):
    """Return PNG bytes of a QR code encoding *data*.

    ``quiet_zone=0`` returns the bare symbol so a receipt can print the symbol
    itself at an exact physical size (S.R.O. 1006: 7x7 mm) and supply the
    white margin around it.
    """
    encoder = qr.QrCodeWidget(str(data)).qr
    encoder.make()
    matrix = encoder.modules
    count = len(matrix)
    quiet = max(0, int(quiet_zone))
    side = (count + 2 * quiet) * module_size

    image = Image.new("1", (side, side), 1)
    pixels = image.load()
    for row, modules in enumerate(matrix):
        for column, is_dark in enumerate(modules):
            if not is_dark:
                continue
            left = (column + quiet) * module_size
            top = (row + quiet) * module_size
            for x in range(left, left + module_size):
                for y in range(top, top + module_size):
                    pixels[x, y] = 0

    buffer = BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()
