"""
SafeBite - Flask backend.
Python does all the heavy work (OCR, decoding, allergen logic, Open Food Facts, e-mail).
The browser (static/js/app.js) talks to it through the JSON API below.

Run:  python app.py      Deploy:  gunicorn app:app
"""
from flask import (Flask, render_template, request, session, redirect, url_for,
                   jsonify, Response, flash)

import config
from database import (init_db, save_user, get_user, add_scan, recent_flagged_scans,
                      recent_scans, clear_scans)
from modules import allergen_engine as ae
from modules import openfoodfacts as off
from modules.barcode_engine import decode_codes, load_image, ean_valid
from modules.ocr_engine import scan_menu, plain
from modules.sos import send_sos, build_card

app = Flask(__name__)
app.secret_key = config.SECRET_KEY
app.config["MAX_CONTENT_LENGTH"] = config.MAX_UPLOAD_MB * 1024 * 1024
init_db()


def current_user():
    return get_user(session.get("uid"))


def _allowed(filename, mimetype=None):
    if mimetype and mimetype.startswith("image/"):
        return True
    if not filename:
        return False
    # camera frames arrive as "frame.jpg"; anything else must have an image extension
    return "." in filename and filename.rsplit(".", 1)[1].lower() in config.ALLOWED_EXT


def err(msg, code=400, **extra):
    return jsonify({"ok": False, "error": msg, **extra}), code


# ================================================================== pages
@app.route("/", methods=["GET", "POST"])
def index():
    user = current_user()
    if request.method == "POST":
        f = request.form
        custom = [a.strip().lower() for a in f.get("custom_allergens", "").split(",") if a.strip()]
        custom_d = [d.strip().lower() for d in f.get("custom_diseases", "").split(",") if d.strip()]
        data = {
            "name": f.get("name", "").strip(),
            "age": int(f["age"]) if f.get("age", "").isdigit() else None,
            "email": f.get("email", "").strip(),
            "diseases": f.getlist("diseases") + custom_d,
            "allergens": sorted(set(f.getlist("allergens") + custom)),
            "ec_name": f.get("ec_name", "").strip(),
            "ec_phone": f.get("ec_phone", "").strip(),
            "ec_email": f.get("ec_email", "").strip(),
        }
        if not data["name"]:
            flash("Please enter your name.")
            return redirect(url_for("index"))
        session["uid"] = save_user(data, session.get("uid"))
        return redirect(url_for("scan"))
    return render_template("index.html", user=user, allergen_list=list(ae.ALLERGENS),
                           disease_list=ae.COMMON_DISEASES)


@app.route("/scan")
def scan():
    user = current_user()
    if not user:
        return redirect(url_for("index"))
    return render_template("scan.html", user=user)


# ================================================================== serializers
def _words(ws):
    return [{"t": w["text"], "low": w["low"]} for w in ws]


def _verdict(a):
    return {"status": a["status"], "reasons": a["reasons"], "found": a["allergens_found"],
            "possible": a["possible"], "detected": a["all_detected"],
            "disease_flags": a["disease_flags"]}


def product_json(code, user):
    product = off.fetch_product(code)
    if not product:
        return {"ok": True, "kind": "notfound", "code": code}
    a = ae.analyze_product(product, user)
    name = product.get("product_name") or code
    add_scan(user["id"], "product", name, a["status"], a["allergens_found"])
    return {"ok": True, "kind": "product", "code": code, "name": name,
            "brand": product.get("brands", ""), "quantity": product.get("quantity", ""),
            "image": product.get("image_front_small_url"),
            "nutriscore": product.get("nutriscore_grade"), "nova": product.get("nova_group"),
            "ingredients": product.get("ingredients_text", ""),
            "nutrition": off.nutrition_summary(product), "verdict": _verdict(a)}


def text_json(text, user, via="Pasted text", confidence=None):
    a = ae.analyze_text(text, user)
    add_scan(user["id"], "text", text[:60], a["status"], a["allergens_found"])
    res = {"ok": True, "kind": "text", "via": via, "text": text, "verdict": _verdict(a)}
    if confidence is not None:
        res["confidence"] = confidence
    return res


def menu_json(img, user, qr_url):
    menu = scan_menu(img)
    raw_text = menu.get("raw_text", "").strip()
    columns, counts = [], {"red": 0, "yellow": 0, "green": 0}
    for col in menu.get("columns", []):
        items = []
        for it in col:
            if it["type"] == "section":
                sec_text = plain(it["words"])
                sec_a = ae.analyze_text(sec_text, user, has_details=True)
                items.append({
                    "type": "section",
                    "words": _words(it["words"]),
                    "text": sec_text,
                    "verdict": _verdict(sec_a) if sec_a["status"] != "green" else None
                })
                continue
            name = plain(it["name"])
            desc = " ".join(plain(d) for d in it["desc"])
            a = ae.analyze_text(f"{name} {desc}", user, has_details=bool(desc.strip()))
            counts[a["status"]] += 1
            if a["status"] != "green" and (a["allergens_found"] or a["possible"]):
                add_scan(user["id"], "menu", name, a["status"], a["allergens_found"] or a["possible"])
            items.append({"type": "dish", "name": _words(it["name"]), "name_text": name,
                          "price": it["price"], "desc": [_words(d) for d in it["desc"]],
                          "verdict": _verdict(a)})
        columns.append(items)

    total_dishes = counts["red"] + counts["yellow"] + counts["green"]
    low_raw = raw_text.lower()
    is_ingredients = any(k in low_raw for k in ["ingredient", "nutrition fact", "serving size", "contains:"])

    # If it's an ingredients label or no dishes were parsed:
    if (is_ingredients or total_dishes == 0) and raw_text:
        return text_json(raw_text, user, via="Photo text OCR", confidence=menu.get("avg_conf", 0))

    if total_dishes == 0 and not raw_text:
        return {"ok": False, "error": "No readable text or barcode was detected in this photo. Please retake the photo in good lighting."}

    return {"ok": True, "kind": "menu", "columns": columns, "counts": counts,
            "confidence": menu.get("avg_conf", 0), "qr_url": qr_url, "raw_text": raw_text}


# ================================================================== API
@app.route("/api/scan", methods=["POST"])
def api_scan():
    user = current_user()
    if not user:
        return err("Create a profile first.", 401)

    mode = request.form.get("mode", "auto")          # "code" = live-camera frames, barcode/QR only
    code = request.form.get("barcode", "").strip().replace(" ", "")
    pasted = request.form.get("ingredients", "").strip()
    file = request.files.get("image")

    if code:
        if not ean_valid(code):
            return err("That barcode number fails its check digit. Re-type it carefully.")
        return jsonify(product_json(code, user))
    if pasted:
        return jsonify(text_json(pasted, user))
    if not file or not file.filename:
        return err("Choose a photo, type a barcode, or paste ingredients.")
    if not _allowed(file.filename, getattr(file, "mimetype", None)):
        return err("Upload a PNG, JPG, WEBP or BMP image.")

    img = load_image(file.read())
    if img is None:
        return err("Could not open that image. Try another photo.")

    codes = decode_codes(img)
    for c in codes:
        if c["kind"] == "product":
            return jsonify(product_json(c["data"], user))
    for c in codes:
        if c["kind"] == "text":
            return jsonify(text_json(c["data"], user, via="QR code"))
    qr_url = next((c["data"] for c in codes if c["kind"] == "url"), None)

    if mode == "code":                                # live camera: keep trying, no OCR
        return jsonify({"ok": False, "retry": True, "error": "No code in view yet."})
    
    result = menu_json(img, user, qr_url)
    if not result.get("ok", True):
        return err(result.get("error", "Could not process image."))
    return jsonify(result)


@app.route("/api/dish-info")
def api_dish_info():
    name = request.args.get("name", "").strip()
    p = off.search_by_name(name) if name else None
    if not p:
        return jsonify({"found": False})
    return jsonify({"found": True, "name": p.get("product_name"), "nutrition": off.nutrition_summary(p)})


@app.route("/api/history", methods=["GET", "DELETE"])
def api_history():
    user = current_user()
    if not user:
        return err("Create a profile first.", 401)
    if request.method == "DELETE":
        clear_scans(user["id"])
    return jsonify({"ok": True, "items": recent_scans(user["id"])})


@app.route("/api/sos", methods=["POST"])
def api_sos():
    user = current_user()
    if not user:
        return err("Create a profile first.", 401)
    try:
        return jsonify(send_sos(user, recent_flagged_scans(user["id"])))
    except Exception as e:                            # SMTP login errors etc.
        return jsonify({"sent": False, "message": f"Could not send e-mail: {e}"}), 500


@app.route("/sos-card.png")
def sos_card():
    user = current_user()
    if not user:
        return redirect(url_for("index"))
    return Response(build_card(user, recent_flagged_scans(user["id"])), mimetype="image/png")


@app.route("/healthz")
def healthz():
    return "ok"


if __name__ == "__main__":
    app.run(debug=True)
