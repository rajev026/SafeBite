"""SOS: draw an emergency ID card as a PNG (Pillow) and e-mail it (smtplib)."""
import io
import os
import smtplib
from datetime import datetime
from email.message import EmailMessage
from PIL import Image, ImageDraw, ImageFont
import config

FONT_CANDIDATES = ["DejaVuSans.ttf", "arial.ttf", "Arial.ttf", "Helvetica.ttc",
                   "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"]
BOLD_CANDIDATES = ["DejaVuSans-Bold.ttf", "arialbd.ttf", "Arial Bold.ttf",
                   "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"]


def _font(size, bold=False):
    for name in (BOLD_CANDIDATES if bold else FONT_CANDIDATES):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default(size)


def _wrap(draw, text, font, max_w):
    lines, cur = [], ""
    for word in text.split():
        trial = (cur + " " + word).strip()
        if draw.textlength(trial, font=font) <= max_w:
            cur = trial
        else:
            lines.append(cur)
            cur = word
    if cur:
        lines.append(cur)
    return lines or [""]


def user_code(user):
    return f"SB-{user['id']:06d}"


def build_card(user, flagged):
    """Return PNG bytes of the emergency card."""
    W, pad = 1000, 40
    probe = ImageDraw.Draw(Image.new("RGB", (W, 10)))
    f_h, f_b, f_s, f_k = _font(46, True), _font(30), _font(26), _font(24, True)

    rows = [("User ID", user_code(user)),
            ("Name", user["name"]),
            ("Age", str(user.get("age") or "-")),
            ("ALLERGIES", ", ".join(user["allergens"]) or "none recorded"),
            ("Conditions", ", ".join(user["diseases"]) or "none recorded")]
    layout, y = [], 170
    for k, v in rows:
        lines = _wrap(probe, v, f_b, W - 2 * pad - 260)
        layout.append((k, lines, y))
        y += max(48, 40 * len(lines)) + 10
    y += 10
    prod_y = y
    items = []
    for f in flagged[:5]:
        txt = f"{f['label']}  -  contains: {', '.join(f['allergens_found'])}"
        lines = _wrap(probe, txt, f_s, W - 2 * pad - 40)
        items.append((lines, y + 50))
        y += 36 * len(lines) + 14
    if not flagged:
        y += 60
    cy = y + 50                      # top of the emergency-contact box
    H = cy + 190

    img = Image.new("RGB", (W, H), "#FFFFFF")
    d = ImageDraw.Draw(img)
    d.rectangle([0, 0, W, 120], fill="#C62828")
    d.text((pad, 34), "SAFEBITE  EMERGENCY ALERT", font=f_h, fill="#FFFFFF")
    d.text((pad, 130), "Possible allergic reaction. Please contact this person now.", font=f_s, fill="#333333")

    for k, lines, yy in layout:
        d.text((pad, yy), k, font=f_k, fill="#666666")
        for i, ln in enumerate(lines):
            d.text((pad + 260, yy - 3 + i * 40), ln, font=f_b, fill="#111111")

    d.line([pad, prod_y - 8, W - pad, prod_y - 8], fill="#CCCCCC", width=2)
    d.text((pad, prod_y), "LAST SCANNED ITEMS WITH ALLERGENS", font=f_k, fill="#C62828")
    if flagged:
        for (lines, yy), f in zip(items, flagged):
            for i, ln in enumerate(lines):
                d.text((pad + 20, yy + i * 36), ("- " if i == 0 else "  ") + ln, font=f_s, fill="#111111")
    else:
        d.text((pad + 20, prod_y + 50), "No flagged scans recorded.", font=f_s, fill="#111111")

    d.rectangle([pad, cy, W - pad, H - 30], outline="#C62828", width=3)
    d.text((pad + 20, cy + 14), "EMERGENCY CONTACT", font=f_k, fill="#C62828")
    d.text((pad + 20, cy + 56), f"{user.get('ec_name') or '-'}   {user.get('ec_phone') or ''}",
           font=f_b, fill="#111111")
    d.text((pad + 20, cy + 106), "Sent " + datetime.now().strftime("%d %b %Y, %H:%M"),
           font=f_s, fill="#666666")

    buf = io.BytesIO()
    img.save(buf, "PNG")
    return buf.getvalue()


def send_sos(user, flagged):
    """E-mail the card. If SMTP is not configured, save it to /outbox instead."""
    png = build_card(user, flagged)
    recipients = [e for e in (user.get("ec_email"), user.get("email")) if e]
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")

    if not (config.SMTP_HOST and config.SMTP_USER and config.SMTP_PASS and recipients):
        os.makedirs(config.OUTBOX_DIR, exist_ok=True)
        path = os.path.join(config.OUTBOX_DIR, f"sos-{user_code(user)}-{stamp}.png")
        with open(path, "wb") as fh:
            fh.write(png)
        return {"sent": False, "saved_to": path,
                "message": "E-mail is not configured (.env). Card saved in the outbox folder."}

    msg = EmailMessage()
    msg["Subject"] = f"SAFEBITE EMERGENCY: {user['name']} may be having an allergic reaction"
    msg["From"] = config.SMTP_USER
    msg["To"] = ", ".join(recipients)
    msg.set_content(
        f"{user['name']} (ID {user_code(user)}) pressed SOS in SafeBite after possibly eating "
        f"something they are allergic to.\nAllergies: {', '.join(user['allergens']) or 'n/a'}\n"
        "The emergency card is attached. Please call them or emergency services immediately.")
    msg.add_attachment(png, maintype="image", subtype="png", filename=f"safebite-sos-{stamp}.png")
    with smtplib.SMTP(config.SMTP_HOST, config.SMTP_PORT, timeout=20) as s:
        s.starttls()
        s.login(config.SMTP_USER, config.SMTP_PASS)
        s.send_message(msg)
    return {"sent": True, "to": recipients, "message": "Emergency card e-mailed."}
