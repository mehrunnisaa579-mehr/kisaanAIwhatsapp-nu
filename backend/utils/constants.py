"""
FarmAI Constants
Centralized crop keywords, disease mappings, and configuration values
used across the multi-agent pipeline.
"""

# ---------------------------------------------------------------------------
# Crop keyword mappings (lowercase)
# ---------------------------------------------------------------------------
CROP_KEYWORDS = {
    "Cotton": [
        "cotton", "کپاس", "kapaas", "کپاس کی فصل",
    ],
    "Wheat": [
        "wheat", "گندم", "gandum",
    ],
    "Mango": [
        "mango", "آم", "aam",
    ],
}

# ---------------------------------------------------------------------------
# Mock disease database per crop
# ---------------------------------------------------------------------------
DISEASE_MAP = {
    "Cotton": {
        "disease": "Possible Cotton Leaf Curl Virus",
        "disease_urdu": "کپاس کے پتوں کے مڑنے کی بیماری کا امکان",
        "confidence": 0.78,
        "risk_level": "Medium",
    },
    "Wheat": {
        "disease": "Possible Yellow Rust",
        "disease_urdu": "گندم میں زرد زنگ کا امکان",
        "confidence": 0.74,
        "risk_level": "Medium",
    },
    "Mango": {
        "disease": "Possible Anthracnose",
        "disease_urdu": "آم میں اینتھراکنوز کا امکان",
        "confidence": 0.76,
        "risk_level": "Medium",
    },
}

UNKNOWN_DISEASE = {
    "disease": "Unknown crop issue",
    "disease_urdu": "فصل کا مسئلہ مکمل طور پر واضح نہیں",
    "confidence": 0.45,
    "risk_level": "Low",
}

# ---------------------------------------------------------------------------
# Language detection helpers
# ---------------------------------------------------------------------------
URDU_CHAR_RANGE = "\u0600-\u06FF"  # Basic Arabic/Urdu block

ROMAN_URDU_WORDS = [
    "fasal", "kisan", "pani", "gandum", "kapaas", "aam",
    "theek", "nahi", "hai", "aur", "mein", "achi", "buri",
    "patton", "patte", "beemar", "dawa", "kharcha",
]

# ---------------------------------------------------------------------------
# Contradiction trigger words (user says "everything is fine")
# ---------------------------------------------------------------------------
HEALTHY_KEYWORDS = [
    "theek", "ٹھیک", "healthy", "no issue", "achi", "اچھی",
    "normal", "fine", "koi masla nahi",
]

# ---------------------------------------------------------------------------
# Budget / cost defaults
# ---------------------------------------------------------------------------
DEFAULT_BUDGET_LIMIT_PKR = 2000

MANGO_TREATMENT_COST_PKR = 4500
MANGO_ALTERNATIVE_COST_PKR = 1200

DEFAULT_TREATMENT_COST_PKR = 1500

# ---------------------------------------------------------------------------
# Image confidence boost
# ---------------------------------------------------------------------------
IMAGE_CONFIDENCE_BOOST = 0.07
MAX_CONFIDENCE = 0.90
LOW_CONFIDENCE_THRESHOLD = 0.55
