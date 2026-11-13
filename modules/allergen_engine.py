"""
Rule engine: decides GREEN / YELLOW / RED for a piece of text (dish description,
ingredient list, QR text) or an Open Food Facts product.

  RED    -> contains something the user is allergic to (named in the result)
  YELLOW -> may contain it / traces / ingredients unknown -> ask the chef
  GREEN  -> nothing found

Disease rules (diabetes, hypertension ...) are evaluated separately and can
only ever raise the colour, never lower it.
"""
import re

# canonical allergen -> words that reveal it in a menu or ingredient list
ALLERGENS = {
    "milk": ["milk", "dairy", "butter", "cheese", "cream", "ghee", "paneer", "curd",
             "yogurt", "yoghurt", "whey", "casein", "lactose", "custard", "khoya",
             "mozzarella", "parmesan", "ricotta", "mascarpone", "buttermilk", "ice cream"],
    "egg": ["egg", "mayonnaise", "mayo", "meringue", "albumin", "aioli", "omelette", "omelet"],
    "peanut": ["peanut", "groundnut", "monkey nut", "arachis"],
    "tree nuts": ["almond", "cashew", "walnut", "pistachio", "hazelnut", "pecan", "macadamia",
                  "brazil nut", "pine nut", "nut", "nuts", "praline", "marzipan", "nutella"],
    "soy": ["soy", "soya", "soybean", "tofu", "edamame", "miso", "tempeh", "soy sauce"],
    "gluten": ["wheat", "gluten", "flour", "maida", "atta", "semolina", "rava", "suji", "barley",
               "rye", "bread", "breadcrumb", "pasta", "noodle", "noodles", "naan", "roti",
               "paratha", "couscous", "pizza base", "bun", "burger bun", "tortilla", "batter"],
    "fish": ["fish", "salmon", "tuna", "cod", "anchovy", "anchovies", "sardine", "mackerel",
             "trout", "fish sauce", "worcestershire"],
    "shellfish": ["shrimp", "prawn", "prawns", "crab", "lobster", "shellfish", "oyster",
                  "clam", "mussel", "squid", "calamari", "scallop", "crustacean", "mollusc"],
    "sesame": ["sesame", "tahini", "til", "gingelly", "hummus"],
    "mustard": ["mustard", "mustard seed"],
    "celery": ["celery", "celeriac"],
    "sulphites": ["sulphite", "sulfite", "sulphur dioxide", "sulfur dioxide", "e220", "e221",
                  "e222", "e223", "e224", "e226", "e227", "e228"],
}

# dish names that usually hide allergens even if the menu does not list them
DISH_HINTS = {
    "alfredo": ["milk", "gluten"], "carbonara": ["egg", "milk", "gluten"],
    "pesto": ["tree nuts", "milk"], "tempura": ["gluten", "egg"], "caesar": ["egg", "fish", "milk"],
    "naan": ["gluten", "milk"], "korma": ["tree nuts", "milk"], "tikka masala": ["milk", "tree nuts"],
    "butter chicken": ["milk", "tree nuts"], "satay": ["peanut", "soy"],
    "pad thai": ["peanut", "egg", "fish", "shellfish", "soy"], "tiramisu": ["egg", "milk", "gluten"],
    "brownie": ["egg", "milk", "gluten", "tree nuts"], "cake": ["egg", "milk", "gluten"],
    "gulab jamun": ["milk", "gluten"], "halwa": ["milk", "tree nuts"], "kheer": ["milk", "tree nuts"],
    "pizza": ["gluten", "milk"], "burger": ["gluten", "egg", "sesame"], "sandwich": ["gluten"],
    "sushi": ["fish", "soy"], "ramen": ["gluten", "soy", "egg"], "dumpling": ["gluten", "soy"],
    "momos": ["gluten", "soy"], "samosa": ["gluten"], "pakora": ["gluten"], "biryani": ["milk"],
    "curry": ["mustard"], "chowmein": ["gluten", "soy", "egg"], "fried rice": ["soy", "egg"],
    "falafel": ["sesame", "gluten"], "hummus": ["sesame"], "pancake": ["gluten", "egg", "milk"],
    "waffle": ["gluten", "egg", "milk"], "milkshake": ["milk"], "ice cream": ["milk", "egg"],
    "cutlet": ["gluten", "egg"], "fish and chips": ["fish", "gluten"],
}

TRACE_CLAUSE_RE = re.compile(
    r"(?:may contain|might contain|traces? of|processed in|produced in a facility|shared (?:equipment|kitchen|fryer))[^.;\n]*",
    re.I)
# words that look like an allergen but are not (or point to a different one)
NEUTRALIZE = [
    (re.compile(r"peanut butter", re.I), "peanut"),
    (re.compile(r"(almond|cashew|hazelnut|nut) butter", re.I), r"\1"),
    (re.compile(r"cocoa butter|shea butter|butternut|butter ?bean", re.I), " "),
    (re.compile(r"coconut (?:milk|cream)|(?:oat|rice) milk|cream of tartar", re.I), " "),
    (re.compile(r"soy(?:a)? milk", re.I), "soy"),
    (re.compile(r"almond milk", re.I), "almond"),
]
FREE_RE = re.compile(r"\b(?:\w+)[\s-]*free\b|\b(?:no|without|free from)\s+\w+", re.I)

# a disease can also imply an allergen-style avoidance
DISEASE_IMPLIES = {
    "celiac disease": ["gluten"],
    "lactose intolerance": ["milk"],
}

DISEASE_WORDS = {
    "diabetes": ["sugar", "syrup", "honey", "jaggery", "glucose", "fructose", "dextrose",
                 "sucrose", "molasses", "caramel", "sweetened", "candied", "chocolate",
                 "dessert", "sweet", "jam", "cola", "soda", "sweetener"],
    "hypertension": ["salt", "salted", "sodium", "msg", "monosodium", "soy sauce", "pickle",
                     "pickled", "brine", "cured", "bacon", "ham", "processed cheese"],
    "high cholesterol / heart disease": ["butter", "ghee", "cream", "lard", "fried", "deep-fried",
                                         "deep fried", "bacon", "cheese", "fatty", "mayonnaise", "mayo"],
}

# thresholds per 100 g (yellow, red) from Open Food Facts nutriments
DISEASE_NUTRIENT_RULES = {
    "diabetes": [("sugars_100g", "sugar", 5, 15, "g"), ("carbohydrates_100g", "carbohydrates", 40, 65, "g")],
    "hypertension": [("salt_100g", "salt", 0.75, 1.5, "g")],
    "high cholesterol / heart disease": [("saturated-fat_100g", "saturated fat", 1.5, 5, "g"),
                                         ("salt_100g", "salt", 0.75, 1.5, "g")],
}

# Open Food Facts tag -> our canonical name
OFF_TAG_MAP = {
    "milk": "milk", "eggs": "egg", "peanuts": "peanut", "nuts": "tree nuts",
    "soybeans": "soy", "gluten": "gluten", "fish": "fish", "crustaceans": "shellfish",
    "molluscs": "shellfish", "sesame-seeds": "sesame", "mustard": "mustard",
    "celery": "celery", "sulphur-dioxide-and-sulphites": "sulphites",
}

COMMON_DISEASES = ["diabetes", "hypertension", "high cholesterol / heart disease",
                   "celiac disease", "lactose intolerance", "asthma", "kidney disease"]
SEVERITY = {"green": 0, "yellow": 1, "red": 2}


# ---------------------------------------------------------------- helpers
def _pattern(word):
    return re.compile(r"(?<![a-z0-9])" + re.escape(word.lower()) + r"(?:s|es)?(?![a-z0-9])")


def keywords_for(allergen):
    """Known keyword list, or just the user's own word for custom allergens."""
    a = allergen.strip().lower()
    return ALLERGENS.get(a, [a])


def find_allergens(text, restrict_to=None):
    """Return {canonical_allergen: [matched words]} found in text."""
    t = text.lower()
    for rx, repl in NEUTRALIZE:
        t = rx.sub(repl, t)
    t = FREE_RE.sub(" ", t)          # "gluten-free", "no nuts", "without egg" are not hits
    found = {}
    names = restrict_to if restrict_to is not None else list(ALLERGENS)
    for name in names:
        for kw in keywords_for(name):
            if _pattern(kw).search(t):
                found.setdefault(name, []).append(kw)
    return found


def effective_allergens(profile):
    """User's allergens + the ones implied by their diseases."""
    out = [a.lower() for a in profile.get("allergens", [])]
    for d in profile.get("diseases", []):
        for a in DISEASE_IMPLIES.get(d.lower(), []):
            if a not in out:
                out.append(a)
    return out


def _worst(a, b):
    return a if SEVERITY[a] >= SEVERITY[b] else b


# ---------------------------------------------------------------- text analysis
def analyze_text(text, profile, has_details=True):
    """
    Analyse free text (dish name + description, ingredient list ...).
    has_details=False means we only have a name, so we cannot be sure.
    """
    mine = effective_allergens(profile)
    result = {"status": "green", "allergens_found": [], "possible": [],
              "all_detected": [], "reasons": [], "disease_flags": []}
    if not text.strip():
        result["status"] = "yellow"
        result["reasons"].append("No readable ingredient information. Ask the chef.")
        return result

    trace_clauses = [m.group(0) for m in TRACE_CLAUSE_RE.finditer(text)]
    main_text = TRACE_CLAUSE_RE.sub(" ", text)          # "may contain milk" is NOT a definite hit
    detected = find_allergens(main_text)                 # everything we can spot (info)
    result["all_detected"] = sorted(detected)

    # RED: user's allergen named in the text
    for a in mine:
        hits = find_allergens(main_text, restrict_to=[a])
        if hits:
            result["allergens_found"].append(a)
            result["reasons"].append(f"Contains {a} (matched: {', '.join(hits[a][:3])}).")
    if result["allergens_found"]:
        result["status"] = "red"

    # YELLOW: "may contain" statements that mention user's allergens
    for clause in trace_clauses:
        for a in mine:
            if a not in result["allergens_found"] and a not in result["possible"] and find_allergens(clause, [a]):
                result["possible"].append(a)
                result["reasons"].append(f"Label says it may contain traces of {a}.")

    # YELLOW: dish names that usually hide an allergen
    low = text.lower()
    for dish, hidden in DISH_HINTS.items():
        if dish in low:
            for a in hidden:
                if a in mine and a not in result["allergens_found"] and a not in result["possible"]:
                    result["possible"].append(a)
                    result["reasons"].append(f"'{dish}' is usually made with {a}. Ask the chef.")
    if result["possible"] and result["status"] == "green":
        result["status"] = "yellow"

    # YELLOW: user has allergens but dish gives no ingredient details at all
    if mine and not has_details and result["status"] == "green":
        result["status"] = "yellow"
        result["reasons"].append("No ingredients listed for this dish. Ask the chef.")

    for f in disease_flags_text(text, profile):
        result["disease_flags"].append(f)
        result["status"] = _worst(result["status"], f["level"])
    return result


def disease_flags_text(text, profile):
    flags, low = [], text.lower()
    for disease in profile.get("diseases", []):
        d = disease.lower()
        words = DISEASE_WORDS.get(d)
        if not words:
            continue
        hits = [w for w in words if _pattern(w).search(low)]
        if hits:
            flags.append({"disease": d, "level": "yellow",
                          "msg": f"May not suit {d}: mentions {', '.join(hits[:3])}."})
    return flags


# ---------------------------------------------------------------- packaged products
def off_allergens(tags):
    out = []
    for t in tags or []:
        key = t.split(":")[-1]
        out.append(OFF_TAG_MAP.get(key, key.replace("-", " ")))
    return sorted(set(out))


def analyze_product(product, profile):
    """Combine ingredient text, OFF allergen tags, traces and nutrition."""
    mine = effective_allergens(profile)
    ingredients = product.get("ingredients_text") or ""
    declared = off_allergens(product.get("allergens_tags"))
    traces = off_allergens(product.get("traces_tags"))

    res = analyze_text(ingredients, profile) if ingredients else {
        "status": "green", "allergens_found": [], "possible": [], "all_detected": [],
        "reasons": [], "disease_flags": []}

    for a in mine:
        if a in declared and a not in res["allergens_found"]:
            res["allergens_found"].append(a)
            res["reasons"].append(f"Declared allergen: {a}.")
        if a in traces and a not in res["allergens_found"] and a not in res["possible"]:
            res["possible"].append(a)
            res["reasons"].append(f"May contain traces of {a}.")
    res["all_detected"] = sorted(set(res["all_detected"]) | set(declared))
    res["traces"] = traces

    if res["allergens_found"]:
        res["status"] = "red"
    elif res["possible"]:
        res["status"] = _worst(res["status"], "yellow")

    if not ingredients and not declared:
        res["reasons"].append("Open Food Facts has no ingredient data for this product. Check the pack.")
        if mine:
            res["status"] = _worst(res["status"], "yellow")

    # nutrition-based disease checks
    nut = product.get("nutriments") or {}
    for disease in profile.get("diseases", []):
        for key, label, y, r, unit in DISEASE_NUTRIENT_RULES.get(disease.lower(), []):
            val = nut.get(key)
            if val is None:
                continue
            if val >= r:
                lvl = "red"
            elif val >= y:
                lvl = "yellow"
            else:
                continue
            res["disease_flags"].append({
                "disease": disease, "level": lvl,
                "msg": f"High {label} for {disease}: {val:.1f}{unit} per 100g."})
            res["status"] = _worst(res["status"], lvl)
    return res
