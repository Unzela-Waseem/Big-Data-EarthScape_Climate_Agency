"""
EarthScape Climate Agency — ML Model Loader
Loads the ensemble models and metadata ONCE at import time.
"""

import os
import json
import pickle
import warnings

# Suppress sklearn version mismatch warnings from the pickle
warnings.filterwarnings("ignore")

# ---------------------------------------------------------------------------
# Paths (relative to this file's directory)
# ---------------------------------------------------------------------------
_BASE_DIR = os.path.dirname(os.path.abspath(__file__))
_PKL_PATH = os.path.join(_BASE_DIR, "model", "direct_models.pkl")
_META_PATH = os.path.join(_BASE_DIR, "model", "metadata.json")

# ---------------------------------------------------------------------------
# Public state — importers read these directly
# ---------------------------------------------------------------------------
MODEL_READY = False          # True when pickle loaded successfully
MODELS = {}                  # {h: {"Ridge": m, "RF": m, "GB": m}}
COLS = []                    # feature column names
PARAMS = {}                  # training hyper-params (informational)
HALFLIFE = None
HALF = {}                    # {h: half-width for prediction interval}
TRAINED_UNTIL = None         # last training date string
HS = []                      # list of horizons [1..12]

METADATA = {}                # contents of metadata.json
META_READY = False

# Feature set C_B+ENSO (canonical order)
FEATURE_COLS = [
    "dev_lag1", "dev_lag2", "dev_lag3", "dev_lag6", "dev_lag12",
    "dev_roll3", "dev_roll6", "vol12",
    "oni_l3", "oni_l4", "oni_l6", "oni_chg",
]

# ---------------------------------------------------------------------------
# Custom Unpickler to bridge sklearn version serialization
# ---------------------------------------------------------------------------
class StubCyHalfSquaredError:
    def __init__(self, *args, **kwargs):
        pass

class CompatibleUnpickler(pickle.Unpickler):
    def find_class(self, module, name):
        if name == "CyHalfSquaredError":
            return StubCyHalfSquaredError
        if module == "_loss":
            try:
                import sklearn._loss as sk_loss
                return getattr(sk_loss, name)
            except Exception:
                return StubCyHalfSquaredError
        return super().find_class(module, name)

# ---------------------------------------------------------------------------
# Load pickle
# ---------------------------------------------------------------------------
try:
    with open(_PKL_PATH, "rb") as fh:
        _deployment = CompatibleUnpickler(fh).load()

    MODELS = _deployment.get("models", {})
    COLS = _deployment.get("cols", FEATURE_COLS)
    PARAMS = _deployment.get("params", {})
    HALFLIFE = _deployment.get("halflife", None)
    HALF = _deployment.get("half", {})
    TRAINED_UNTIL = _deployment.get("trained_until", None)
    HS = _deployment.get("hs", list(range(1, 13)))
    MODEL_READY = True
    print("[model_loader] Pickle loaded — models ready for horizons", HS)

except FileNotFoundError:
    print("[model_loader] model/direct_models.pkl not found — predictions disabled.")
except Exception as exc:  # noqa: BLE001
    print(f"[model_loader] Error loading pickle: {exc}")

# ---------------------------------------------------------------------------
# Load metadata.json
# ---------------------------------------------------------------------------
try:
    with open(_META_PATH, "r", encoding="utf-8") as fh:
        _raw = json.load(fh)

    METADATA = {
        "feature_set": _raw.get("feature_set", "C_B+ENSO"),
        "target": _raw.get("target", "temp_anomaly"),
        "horizons": _raw.get("horizons", list(range(1, 13))),
        "champion": _raw.get("champion", "Ensemble"),
        "metrics": _raw.get("metrics", {}),
        "trained_until": _raw.get("trained_until", TRAINED_UNTIL),
        "description": _raw.get("description", ""),
    }
    META_READY = True
    print("[model_loader] metadata.json loaded.")

except FileNotFoundError:
    print("[model_loader] model/metadata.json not found — metadata unavailable.")
except Exception as exc:  # noqa: BLE001
    print(f"[model_loader] Error loading metadata: {exc}")
