"""
Menu OCR. Pipeline:
  1. clean the photo (upscale, grayscale, denoise, deskew, contrast)
  2. run Tesseract on two cleaned versions x two page-segmentation modes
     and keep the run with the best confidence
  3. rebuild the layout: words -> segments -> columns -> sections -> dishes

Text is NEVER spell-corrected or paraphrased. Every word is kept exactly as
Tesseract read it; words it is unsure about are flagged (low=True) so the UI can
underline them instead of silently "fixing" them.
"""
import re
import cv2
import numpy as np
import pytesseract
from statistics import median
from config import TESSERACT_CMD, OCR_LOW_CONF

if TESSERACT_CMD:
    pytesseract.pytesseract.tesseract_cmd = TESSERACT_CMD

PRICE_RE = re.compile(
    r"^(?P<name>.*?\S)\s*(?P<price>(?:₹|Rs\.?|INR|\$|€|£)?\s?\d{1,5}(?:[.,]\d{1,2})?(?:\s?/-|\s?₹)?)\s*$",
    re.I)


# ------------------------------------------------------------ 1. image clean-up
def _deskew(gray):
    try:
        inv = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)[1]
        coords = np.column_stack(np.where(inv > 0)[::-1])
        if len(coords) < 500:
            return gray
        rect = cv2.minAreaRect(coords)
        angle = rect[-1]
        angle = -(90 + angle) if angle < -45 else -angle
        if abs(angle) < 0.5 or abs(angle) > 15:       # ignore noise and wild guesses
            return gray
        h, w = gray.shape
        m = cv2.getRotationMatrix2D((w / 2, h / 2), angle, 1.0)
        return cv2.warpAffine(gray, m, (w, h), flags=cv2.INTER_CUBIC,
                              borderMode=cv2.BORDER_REPLICATE)
    except Exception:
        return gray


def preprocess(img_bgr):
    """Return cleaned grayscale versions of the menu photo."""
    h, w = img_bgr.shape[:2]
    if w > 2400:
        scale = 2200 / w
        img_bgr = cv2.resize(img_bgr, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
    elif w < 1000:
        scale = min(2.0, 1600 / w)
        img_bgr = cv2.resize(img_bgr, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)

    gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
    if np.mean(gray) < 110:                        # light text on dark background
        gray = cv2.bitwise_not(gray)

    denoised = cv2.bilateralFilter(gray, 7, 50, 50)
    deskewed = _deskew(denoised)
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8)).apply(deskewed)
    binary = cv2.adaptiveThreshold(clahe, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                                   cv2.THRESH_BINARY, 41, 15)
    return {"contrast": clahe, "gray": deskewed, "binary": binary}


# ------------------------------------------------------------ 2. run tesseract
def _run(img, psm):
    try:
        cfg = f"--oem 3 --psm {psm} -c preserve_interword_spaces=1"
        d = pytesseract.image_to_data(img, config=cfg, output_type=pytesseract.Output.DICT)
    except Exception:
        return []
    words = []
    for i, txt in enumerate(d.get("text", [])):
        txt_s = txt.strip()
        if not txt_s:
            continue
        try:
            conf = float(d["conf"][i])
        except (ValueError, TypeError, KeyError):
            conf = 0.0
        if conf < 0:
            continue
        words.append({"text": txt_s, "conf": conf,
                      "x": int(d["left"][i]), "y": int(d["top"][i]),
                      "w": int(d["width"][i]), "h": int(d["height"][i]),
                      "line": (d["block_num"][i], d["par_num"][i], d["line_num"][i])})
    return words


def read_words(img_bgr):
    best, best_score = [], -1
    preprocessed = preprocess(img_bgr)
    for key in ("contrast", "gray", "binary"):
        img = preprocessed[key]
        for psm in (3, 6):
            words = _run(img, psm)
            if not words:
                continue
            score = np.mean([w["conf"] for w in words]) * np.log1p(len(words))
            if score > best_score:
                best, best_score = words, score
    return best


# ------------------------------------------------------------ 3. layout rebuild
def _segments(words):
    """Split Tesseract lines wherever there is a wide horizontal gap (= another column)."""
    by_line = {}
    for w in words:
        by_line.setdefault(w["line"], []).append(w)
    segs = []
    for ws in by_line.values():
        ws.sort(key=lambda w: w["x"])
        lh = median(w["h"] for w in ws)
        cur = [ws[0]]
        for prev, w in zip(ws, ws[1:]):
            if w["x"] - (prev["x"] + prev["w"]) > lh * 3.0:
                segs.append(cur)
                cur = []
            cur.append(w)
        segs.append(cur)
    out = []
    for s in segs:
        x0 = min(w["x"] for w in s)
        x1 = max(w["x"] + w["w"] for w in s)
        y0 = min(w["y"] for w in s)
        y1 = max(w["y"] + w["h"] for w in s)
        out.append({"words": s, "x0": x0, "x1": x1, "y0": y0, "y1": y1, "h": median(w["h"] for w in s)})
    return out


def _column_bounds(segs, width):
    """Vertical white gaps that run the whole page height are column separators."""
    occ = np.zeros(width + 1, dtype=np.int32)
    for s in segs:
        occ[s["x0"]:s["x1"] + 1] += 1
    min_gap = int(width * 0.04)
    bounds, run_start = [], None
    lo, hi = int(width * 0.15), int(width * 0.85)
    for x in range(lo, hi):
        if occ[x] == 0:
            run_start = x if run_start is None else run_start
        else:
            if run_start is not None and x - run_start >= min_gap:
                bounds.append((run_start + x) // 2)
            run_start = None
    return bounds


def _price_split(text):
    m = PRICE_RE.match(text)
    if m and re.search(r"\d", m.group("price")):
        price_str = m.group("price").strip()
        name_str = m.group("name").strip()
        # If no explicit currency symbol or suffix is present:
        if not re.search(r"₹|Rs|INR|\$|€|£|/-", price_str, re.I):
            # Avoid matching weights/measures/units (e.g. 500g, 100ml, 50%, 100mg) or long numbers/dates
            if len(price_str) > 4 or re.search(r"\d+\s*(?:g|kg|ml|l|oz|lb|mg|kcal|cal|%)\b", text, re.I):
                return text, None
        return name_str, price_str
    return text, None


def _mk_words(ws):
    return [{"text": w["text"], "low": w["conf"] < OCR_LOW_CONF} for w in ws]


def build_menu(words, img_width):
    """Return {'columns': [[{'type':'section'|'dish', ...}]], 'raw_text': str, 'avg_conf': float}"""
    if not words:
        return {"columns": [], "raw_text": "", "avg_conf": 0}
    segs = _segments(words)
    bounds = _column_bounds(segs, img_width)
    ncols = len(bounds) + 1
    cols = [[] for _ in range(ncols)]
    for s in segs:
        idx = sum(1 for b in bounds if s["x0"] >= b)
        cols[min(idx, ncols - 1)].append(s)

    body_h = median(s["h"] for s in segs)
    result_cols = []
    for col in cols:
        col.sort(key=lambda s: (s["y0"], s["x0"]))
        # merge segments that sit on the same visual row inside the column
        rows = []
        for s in col:
            if rows and abs(s["y0"] - rows[-1]["y0"]) < s["h"] * 0.6:
                rows[-1]["words"] += s["words"]
                rows[-1]["x1"] = max(rows[-1]["x1"], s["x1"])
                rows[-1]["y1"] = max(rows[-1]["y1"], s["y1"])
            else:
                rows.append(dict(s))
        items, dish = [], None
        prev_y1 = None
        for r in rows:
            r["words"].sort(key=lambda w: w["x"])
            text = " ".join(w["text"] for w in r["words"])
            name_txt, price = _price_split(text)
            gap = (r["y0"] - prev_y1) if prev_y1 is not None else 9999
            prev_y1 = r["y1"]
            big = r["h"] > body_h * 1.35
            if big and price is None:
                dish = None
                items.append({"type": "section", "words": _mk_words(r["words"])})
            elif price is not None:
                n = len(name_txt.split())
                nw = r["words"][:n] if n else r["words"]
                dish = {"type": "dish", "name": _mk_words(nw), "price": price, "desc": []}
                items.append(dish)
            elif dish is None or gap > r["h"] * 1.8:
                dish = {"type": "dish", "name": _mk_words(r["words"]), "price": None, "desc": []}
                items.append(dish)
            else:
                dish["desc"].append(_mk_words(r["words"]))
        result_cols.append(items)

    raw = " ".join(w["text"] for w in sorted(words, key=lambda w: (w["y"], w["x"])))
    return {"columns": result_cols, "raw_text": raw,
            "avg_conf": round(float(np.mean([w["conf"] for w in words])), 1)}


def scan_menu(img_bgr):
    h, w = img_bgr.shape[:2]
    if w > 2400:
        pw = 2200
    elif w < 1000:
        pw = int(w * min(2.0, 1600 / w))
    else:
        pw = w
    words = read_words(img_bgr)
    return build_menu(words, pw)


def plain(words):
    """Join word dicts back to the exact string Tesseract read."""
    return " ".join(w["text"] for w in words)
