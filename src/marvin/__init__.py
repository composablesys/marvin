from .settings import settings

from .ai.text import (
    predicate,
    val_contract,
    match,
    fn,
    cast,
    cast_async,
    extract,
    extract_async,
    classify,
    classify_async,
    classifier,
    generate,
    generate_async,
    model,
    Model,
    NaturalLangType,
    func_contract,
)
from .ai.images import paint, image
from .ai.audio import speak_async, speak, speech, transcribe, transcribe_async

if settings.auto_import_beta_modules:
    from . import beta

try:
    from ._version import version as __version__
except ImportError:
    __version__ = "unknown"


__all__ = [
    # --- text ---
    "Model",
    "NaturalLangType",
    "cast",
    "cast_async",
    "classify",
    "classify_async",
    "classifier",
    "extract",
    "extract_async",
    "fn",
    "predicate",
    "val_contract",
    "func_contract",
    "match",
    "generate",
    "generate_async",
    "model",
    # --- images ---
    "image",
    "paint",
    # --- audio ---
    "speak",
    "speak_async",
    "speech",
    "transcribe",
    "transcribe_async",
    # --- beta ---
]

if settings.auto_import_beta_modules:
    __all__.append("beta")

# compatibility with Marvin v1
ai_fn = fn
ai_model = model
ai_classifier = classifier
