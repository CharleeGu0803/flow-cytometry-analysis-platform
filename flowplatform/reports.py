import io

from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

from .analysis import channel_values, count_in_polygon, gate_polygon, load_sample, native_scale


def batch_report_pdf(batch, panel):
    """Render a PDF listing the cell count of every configured gate for each file in the batch."""
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=letter)
    c.setFont('Helvetica', 12)
    y = 750

    def new_line(step):
        nonlocal y
        y -= step
        if y < 100:
            c.showPage()
            c.setFont('Helvetica', 12)
            y = 750

    c.drawString(80, y, f'Batch report: {batch.batch_name}')
    new_line(30)

    for f in batch.files:
        c.line(80, y, 530, y)
        new_line(30)
        c.drawString(100, y, f'FCS file: {f.file_name}')
        new_line(20)
        try:
            frames = load_sample(f.file_path)
        except Exception as e:
            c.drawString(120, y, f'Could not read file: {e}')
            new_line(15)
            continue
        for gate in panel['gates']:
            try:
                sx, sy = native_scale(gate['ch_X']), native_scale(gate['ch_Y'])
                x = channel_values(frames, panel, gate['ch_X'], sx)
                yy = channel_values(frames, panel, gate['ch_Y'], sy)
                count = count_in_polygon(x, yy, gate_polygon(gate, sx, sy))
                text = f"Gate: {gate['gate_name'].strip()}, Cell count: {count}"
            except (KeyError, ValueError, OSError) as e:
                text = f"Gate: {gate['gate_name'].strip()}, error: {e}"
            c.drawString(120, y, text)
            new_line(15)

    c.save()
    buf.seek(0)
    return buf
