"""
Barcode + QR detection. Three independent decoders are tried on several
pre-processed versions of the image, and EAN/UPC codes are verified with their
check digit, so a misread never reaches the user.
"""
import re
import cv2
import numpy as np

try:
    from pyzbar import pyzbar
    HAVE_ZBAR = True
except Exception:       # library or DLL missing -> we fall back to OpenCV only
    HAVE_ZBAR = False


def ean_valid(code):
    """Check digit test for EAN-8, UPC-A (12), EAN-13 and GTIN-14."""
    if not code.isdigit() or len(code) not in (8, 12, 13, 14):
        return False
    digits = [int(c) for c in code]
    check = digits.pop()
    total = sum(d * (3 if i % 2 == 0 else 1) for i, d in enumerate(reversed(digits)))
    return (10 - total % 10) % 10 == check


def _variants(img):
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    yield "original", img
    yield "gray", gray
    if gray.shape[1] < 1200:
        big = cv2.resize(gray, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC)
        yield "x2", big
    yield "otsu", cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)[1]
    yield "adaptive", cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                                            cv2.THRESH_BINARY, 31, 10)
    blur = cv2.GaussianBlur(gray, (0, 0), 3)
    yield "sharp", cv2.addWeighted(gray, 1.8, blur, -0.8, 0)
    yield "rot90", cv2.rotate(gray, cv2.ROTATE_90_CLOCKWISE)


def _try_pyzbar(v, found):
    if not HAVE_ZBAR:
        return
    for obj in pyzbar.decode(v):
        data = obj.data.decode("utf-8", errors="ignore").strip()
        if data:
            found[data] = obj.type


def _try_qr(v, found):
    det = cv2.QRCodeDetector()
    try:
        ok, infos, _, _ = det.detectAndDecodeMulti(v)
        if ok:
            for s in infos:
                if s:
                    found[s.strip()] = "QRCODE"
            return
    except cv2.error:
        pass
    s, _, _ = det.detectAndDecode(v)
    if s:
        found[s.strip()] = "QRCODE"


def _try_cv_barcode(v, found):
    try:
        det = cv2.barcode.BarcodeDetector()
        out = det.detectAndDecode(v)
        if len(out) == 4:
            ok, infos, types, _ = out
            if ok:
                for s, t in zip(infos, types):
                    if s:
                        found[s.strip()] = str(t) or "BARCODE"
    except (AttributeError, cv2.error):
        pass


def decode_codes(img_bgr):
    """Return a list of {'data', 'type', 'kind'} dicts. kind: product / url / text."""
    found = {}
    for _, v in _variants(img_bgr):
        _try_pyzbar(v, found)
        _try_qr(v, found)
        _try_cv_barcode(v, found)
        if any(ean_valid(d) for d in found):
            break                    # a verified product barcode is good enough

    results = []
    for data, typ in found.items():
        if data.isdigit() and len(data) in (8, 12, 13, 14):
            if not ean_valid(data):
                continue             # misread digits -> discard
            kind = "product"
        elif re.match(r"https?://", data, re.I):
            kind = "url"
        else:
            kind = "text"
        results.append({"data": data, "type": typ, "kind": kind})
    results.sort(key=lambda r: {"product": 0, "text": 1, "url": 2}[r["kind"]])
    return results


def load_image(file_bytes):
    arr = np.frombuffer(file_bytes, np.uint8)
    return cv2.imdecode(arr, cv2.IMREAD_COLOR)
