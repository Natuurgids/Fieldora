import json

from natureai_next.infrastructure.database import suggestion_generation


def _row(row_id: int, providers: tuple[str, ...], activated: int):
    row = [None] * 12
    row[0] = row_id
    row[10] = json.dumps({"providers": providers})
    row[11] = activated
    return tuple(row)


def test_cuda_variant_is_selected_when_runtime_is_available(monkeypatch) -> None:
    monkeypatch.setattr(suggestion_generation, "_cuda_runtime_available", lambda: True)
    rows = [_row(2, ("CPUExecutionProvider",), 20), _row(1, ("CUDAExecutionProvider",), 20)]
    assert suggestion_generation._select_best_active_variant(rows)[0] == 1


def test_cpu_variant_is_selected_when_cuda_is_unavailable(monkeypatch) -> None:
    monkeypatch.setattr(suggestion_generation, "_cuda_runtime_available", lambda: False)
    rows = [_row(2, ("CPUExecutionProvider",), 20), _row(1, ("CUDAExecutionProvider",), 20)]
    assert suggestion_generation._select_best_active_variant(rows)[0] == 2


def test_selection_never_falls_back_to_an_older_package(monkeypatch) -> None:
    monkeypatch.setattr(suggestion_generation, "_cuda_runtime_available", lambda: False)
    rows = [_row(3, ("CUDAExecutionProvider",), 20), _row(2, ("CPUExecutionProvider",), 10)]
    assert suggestion_generation._select_best_active_variant(rows)[0] == 3
