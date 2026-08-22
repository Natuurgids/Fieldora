"""Prime, validate, and activate the Full AI NatureAI/BioCLIP engine."""

from __future__ import annotations

import argparse
import time

import natureai_next
from natureai_next.bootstrap.paths import resolve_application_paths
from natureai_next.infrastructure.ai.engine_state import NatureAIEngineState, write_engine_state
from natureai_next.infrastructure.ai.tree_of_life_resources import bootstrap_tree_of_life_resources


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config-root", default=None)
    args = parser.parse_args()
    result = bootstrap_tree_of_life_resources(device="cpu")
    paths = resolve_application_paths(
        None if args.config_root is None else __import__("pathlib").Path(args.config_root)
    )
    state_path = paths.subsystem_databases_dir / "natureai.sqlite"
    write_engine_state(
        state_path,
        NatureAIEngineState(
            ready=result.ready,
            engine_version=natureai_next.__version__,
            provider="pybioclip",
            model_identity=result.model_identity,
            model_version="bioclip-v1",
            variant_identity="cuda-fp16" if __import__("torch").cuda.is_available() else "cpu-fp32",
            classifier="TreeOfLifeClassifier",
            taxonomy_source="TreeOfLife-10M",
            taxa_count=result.taxa_count,
            device="cuda" if __import__("torch").cuda.is_available() else "cpu",
            updated_at_us=int(time.time() * 1_000_000),
        ),
    )
    count = "unknown" if result.taxa_count is None else f"{result.taxa_count:,}"
    print(f"Tree-of-Life ready: {result.ready}")
    print(f"Model: {result.model_identity}")
    print(f"Taxa: {count}")
    print(f"NatureAI state: {state_path}")
    print(result.note)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
