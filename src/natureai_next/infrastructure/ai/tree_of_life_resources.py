"""Installation-time bootstrap for the original NatureAI Tree-of-Life engine."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class TreeOfLifeBootstrapResult:
    ready: bool
    taxa_count: int | None
    model_identity: str
    note: str


def bootstrap_tree_of_life_resources(*, device: str = "cpu") -> TreeOfLifeBootstrapResult:
    """Download/cache and validate BioCLIP v1's matching TreeOfLife-10M assets.

    Constructing ``TreeOfLifeClassifier`` is the supported pybioclip resource
    bootstrap. It resolves the original model and its matching precomputed
    TreeOfLife-10M label embeddings through the Hugging Face cache. We then read
    label data when the installed pybioclip version exposes that API, ensuring an
    empty or incompatible cache is never reported as ready.
    """
    try:
        from bioclip import BIOCLIP_V1_MODEL_STR
        from bioclip.predict import TreeOfLifeClassifier
    except ImportError as exc:
        raise RuntimeError(
            "pybioclip is not installed. Install or repair the Full AI environment."
        ) from exc

    try:
        classifier = TreeOfLifeClassifier(
            model_str=BIOCLIP_V1_MODEL_STR,
            device=device,
        )
    except Exception as exc:
        raise RuntimeError(
            f"The original BioCLIP TreeOfLife-10M resources could not be acquired or opened: {exc}"
        ) from exc

    taxa_count: int | None = None
    getter = getattr(classifier, "get_label_data", None)
    if callable(getter):
        try:
            labels: Any = getter()
            taxa_count = len(labels)
            if taxa_count < 1:
                raise RuntimeError("pybioclip returned an empty Tree-of-Life label table.")
        except TypeError:
            # Some pybioclip releases expose rank as a required argument. The
            # successful classifier construction has already validated the
            # model/embedding bundle, so retain an unknown count.
            taxa_count = None
        except Exception as exc:
            raise RuntimeError(f"TreeOfLife-10M label validation failed: {exc}") from exc

    note = (
        "Original BioCLIP model and TreeOfLife-10M labels/embeddings are cached "
        "and managed by pybioclip. GBIF and CSV taxonomy remain optional enrichment."
    )
    return TreeOfLifeBootstrapResult(True, taxa_count, str(BIOCLIP_V1_MODEL_STR), note)
