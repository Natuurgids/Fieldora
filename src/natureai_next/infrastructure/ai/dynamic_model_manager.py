"""On-demand model installation, import, activation and memory cleanup."""

from __future__ import annotations

import gc
import hashlib
import importlib
import importlib.machinery
import importlib.util
import inspect
import json
import shutil
import subprocess
import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from natureai_next.infrastructure.ai.model_catalog import ModelCatalog, ModelSpec


@dataclass(slots=True)
class LoadedModel:
    spec: ModelSpec
    instance: object
    loaded_value: object | None = None


@dataclass(frozen=True, slots=True)
class ModelInstallResult:
    key: str
    installed_dependencies: tuple[str, ...]
    health_detail: str


class DynamicModelManager:
    """Small runtime registry that hooks into existing providers without replacing them."""

    def __init__(
        self, catalog: ModelCatalog, runtime_root: Path, *, capability_router: object | None = None
    ) -> None:
        self.catalog = catalog
        self.runtime_root = runtime_root
        self.runtime_root.mkdir(parents=True, exist_ok=True)
        self._capability_router = capability_router
        self._loaded: dict[str, LoadedModel] = {}
        self._active_keys = self._read_active_keys()
        self._lock = threading.RLock()
        self._restore_active_capabilities()

    def _refresh_active_keys(self) -> None:
        disk_keys = self._read_active_keys()
        if disk_keys != self._active_keys:
            self._active_keys = disk_keys
            self._restore_active_capabilities()

    @property
    def active_key(self) -> str:
        self._refresh_active_keys()
        if self.catalog.default_key in self._active_keys:
            return self.catalog.default_key
        return next(iter(sorted(self._active_keys)), self.catalog.default_key)

    @property
    def active_keys(self) -> frozenset[str]:
        self._refresh_active_keys()
        return frozenset(self._active_keys)

    def activate(self, key: str) -> None:
        spec = self.catalog.get(key)
        if not spec.built_in and not self.is_installed(key):
            raise RuntimeError("Load this model before activating it.")
        if not spec.built_in:
            instance = self.instantiate(key)
            descriptor = getattr(instance, "descriptor", None)
            replace = getattr(self._capability_router, "replace", None)
            if descriptor is not None and callable(replace):
                replace(instance, active=True)
        # One active provider per overlapping capability. Models for unrelated
        # media types remain active together.
        new_assets = set(spec.input_contract.get("asset_types", ()))
        new_output = str(spec.output_contract.get("enrichment_type") or "")
        for active_key in tuple(self._active_keys):
            if active_key == key:
                continue
            active_spec = self.catalog.get(active_key)
            active_assets = set(active_spec.input_contract.get("asset_types", ()))
            active_output = str(active_spec.output_contract.get("enrichment_type") or "")
            if new_output and active_output == new_output and new_assets.intersection(active_assets):
                self._active_keys.discard(active_key)
        self._active_keys.add(key)
        self._write_state()

    def available(self) -> tuple[ModelSpec, ...]:
        return self.catalog.list()

    def missing_dependencies(self, key: str) -> tuple[str, ...]:
        spec = self.catalog.get(key)
        dependency_dir = self._dependency_dir(key)

        def available(import_name: str) -> bool:
            if importlib.util.find_spec(import_name) is not None:
                return True
            if not dependency_dir.is_dir():
                return False
            return (
                importlib.machinery.PathFinder.find_spec(import_name, [str(dependency_dir)])
                is not None
            )

        return tuple(
            item.pip_requirement for item in spec.requirements if not available(item.import_name)
        )

    def install_dependencies(self, key: str) -> tuple[str, ...]:
        missing = self.missing_dependencies(key)
        if not missing:
            return ()
        target = self._dependency_dir(key)
        target.mkdir(parents=True, exist_ok=True)
        command = [
            sys.executable,
            "-m",
            "pip",
            "install",
            "--disable-pip-version-check",
            "--retries",
            "8",
            "--timeout",
            "30",
            "--target",
            str(target),
            *missing,
        ]
        completed = subprocess.run(command, check=False, capture_output=True, text=True)
        if completed.returncode != 0:
            raise RuntimeError(
                (
                    completed.stderr or completed.stdout or "pip dependency installation failed"
                ).strip()
            )
        self._enable_dependency_path(key)
        importlib.invalidate_caches()
        unresolved = self.missing_dependencies(key)
        if unresolved:
            raise RuntimeError(
                "Dependencies installed but imports remain unavailable: " + ", ".join(unresolved)
            )
        return missing

    def install_model(
        self,
        key: str,
        *,
        accept_license: bool = False,
        progress=None,
        cancellation=None,
    ) -> ModelInstallResult:
        """Install dependencies, acquire weights through the provider, and health-check.

        The installed marker is written only after the provider health check succeeds.
        A failed attempt leaves any previously accepted runtime active and unmodified.
        """
        spec = self.catalog.get(key)
        if spec.requires_license_acceptance and not accept_license:
            raise PermissionError(f"{spec.display_name} requires licence acceptance.")
        report = progress if callable(progress) else lambda _current, _total, _message: None
        report(1, 4, "Installing isolated dependencies")
        missing = self.missing_dependencies(key)
        staging = self.runtime_root / f".{key}.installing"
        staged_dependency_path = staging / "site-packages"
        if missing:
            shutil.rmtree(staging, ignore_errors=True)
            staged_dependency_path.mkdir(parents=True, exist_ok=True)
            try:
                self._install_requirements(
                    missing,
                    staged_dependency_path,
                    progress=report,
                    cancellation=cancellation,
                )
            except Exception:
                shutil.rmtree(staging, ignore_errors=True)
                raise
            importlib.invalidate_caches()
        report(2, 4, "Loading model provider")
        instance = self.instantiate(
            key,
            dependency_root=staged_dependency_path if missing else self._dependency_dir(key),
            artifact_root=(staging if missing else self.runtime_root / key) / "artifacts",
        )
        configure_runtime = getattr(instance, "configure_runtime", None)
        report(3, 4, "Acquiring model files and running health check")
        contextual_health_check = getattr(instance, "health_check_with_context", None)
        health_check = getattr(instance, "health_check", None)
        if not callable(contextual_health_check) and not callable(health_check):
            raise TypeError(f"model {key!r} does not expose health_check()")
        try:
            if callable(contextual_health_check):
                detail = str(
                    contextual_health_check(cancellation=cancellation, progress=report) or "ready"
                )
            else:
                detail = str(health_check() or "ready")
            artifact_checksums = self._artifact_checksums(instance)
        except Exception:
            self.unload(key)
            shutil.rmtree(staging, ignore_errors=True)
            raise
        if missing:
            target = self.runtime_root / key
            previous = self.runtime_root / f".{key}.previous"
            shutil.rmtree(previous, ignore_errors=True)
            if target.exists():
                target.replace(previous)
            staging.replace(target)
            shutil.rmtree(previous, ignore_errors=True)
            if callable(configure_runtime):
                self._configure_instance(instance, target / "artifacts", self._dependency_dir(key))
        marker = {
            "schema_version": 1,
            "key": key,
            "version": spec.version,
            "installed_at_us": time.time_ns() // 1_000,
            "health": "ready",
            "health_detail": detail,
            "license_accepted": bool(accept_license),
            "artifact_checksums": artifact_checksums,
        }
        self._model_state_path(key).parent.mkdir(parents=True, exist_ok=True)
        temporary = self._model_state_path(key).with_suffix(".json.new")
        temporary.write_text(json.dumps(marker, indent=2, sort_keys=True), encoding="utf-8")
        temporary.replace(self._model_state_path(key))
        report(4, 4, "Model ready")
        return ModelInstallResult(key, missing, detail)

    def is_installed(self, key: str) -> bool:
        spec = self.catalog.get(key)
        if spec.built_in:
            return not self.missing_dependencies(key)
        try:
            state = json.loads(self._model_state_path(key).read_text(encoding="utf-8"))
        except (OSError, ValueError, json.JSONDecodeError):
            return False
        return state.get("health") == "ready" and state.get("version") == spec.version

    def installation_detail(self, key: str) -> str | None:
        try:
            value = json.loads(self._model_state_path(key).read_text(encoding="utf-8"))
        except (OSError, ValueError, json.JSONDecodeError):
            return None
        detail = value.get("health_detail")
        checksums = value.get("artifact_checksums")
        suffix = (
            f"; {len(checksums)} artifact checksum(s) recorded"
            if isinstance(checksums, dict) and checksums
            else ""
        )
        return f"{detail}{suffix}" if detail else None

    def instantiate(
        self,
        key: str,
        *,
        dependency_root: Path | None = None,
        artifact_root: Path | None = None,
    ) -> object:
        with self._lock:
            resident = self._loaded.get(key)
            if resident is not None:
                configure_runtime = getattr(resident.instance, "configure_runtime", None)
                if callable(configure_runtime) and (
                    dependency_root is not None or artifact_root is not None
                ):
                    self._configure_instance(
                        resident.instance,
                        artifact_root or self.runtime_root / key / "artifacts",
                        dependency_root or self._dependency_dir(key),
                    )
                return resident.instance
            spec = self.catalog.get(key)
            module_name, separator, attribute = spec.factory.partition(":")
            if not separator:
                raise ValueError(f"factory must use module:attribute syntax: {spec.factory}")
            if not module_name.startswith("natureai_next."):
                self._enable_dependency_path(key)
            factory = getattr(importlib.import_module(module_name), attribute)
            instance = factory(**spec.factory_kwargs) if callable(factory) else factory
            configure_runtime = getattr(instance, "configure_runtime", None)
            if callable(configure_runtime):
                self._configure_instance(
                    instance,
                    artifact_root or self.runtime_root / key / "artifacts",
                    dependency_root or self._dependency_dir(key),
                )
            self._loaded[key] = LoadedModel(spec, instance)
            return instance

    def load_generic(self, key: str, **kwargs: Any) -> object:
        with self._lock:
            instance = self.instantiate(key)
            resident = self._loaded[key]
            if resident.loaded_value is None:
                load = getattr(instance, "load", None)
                resident.loaded_value = load(**kwargs) if callable(load) else instance
            return resident.loaded_value

    def infer(
        self, key: str, inputs: object, parameters: dict[str, object] | None = None
    ) -> object:
        model = self.load_generic(key)
        instance = self._loaded[key].instance
        infer = getattr(instance, "infer", None)
        if not callable(infer):
            raise TypeError(f"model {key!r} does not expose infer(inputs, parameters)")
        return infer(inputs, parameters or {}, model=model)

    def unload(self, key: str) -> None:
        with self._lock:
            resident = self._loaded.pop(key, None)
        if resident is None:
            return
        unload = getattr(resident.instance, "unload", None)
        if callable(unload):
            try:
                unload(resident.loaded_value)
            except TypeError:
                unload()
        resident.loaded_value = None
        resident.instance = None  # type: ignore[assignment]
        gc.collect()
        self._clear_torch_cache()

    def deactivate(self, key: str, *, delete_files: bool = False) -> None:
        instance_capability = self._capability_id(key)
        self.unload(key)
        if instance_capability is not None:
            remove = getattr(self._capability_router, "remove", None)
            if callable(remove):
                try:
                    remove(instance_capability)
                except KeyError:
                    pass
        self._active_keys.discard(key)
        if not self._active_keys:
            self._active_keys.add(self.catalog.default_key)
        self._write_state()
        if delete_files:
            shutil.rmtree(self.runtime_root / key, ignore_errors=True)

    def provider(self, key: str | None = None) -> object:
        chosen = key or self.active_key
        instance = self.instantiate(chosen)
        required = (
            "diagnostics",
            "load",
            "embed_images",
            "embed_text",
            "unload",
            "clear_device_cache",
        )
        missing = [name for name in required if not callable(getattr(instance, name, None))]
        if missing:
            raise TypeError(
                f"model {chosen!r} is not an Aperture AI execution provider: {', '.join(missing)}"
            )
        return instance

    @property
    def _state_path(self) -> Path:
        return self.runtime_root / "state.json"

    def _read_active_keys(self) -> set[str]:
        try:
            state = json.loads(self._state_path.read_text(encoding="utf-8"))
            values = state.get("active_models")
            if not isinstance(values, list):
                legacy = state.get("active_model")
                values = [legacy] if legacy else []
            valid = {str(value) for value in values if value and self._known(str(value))}
            if valid:
                return valid
        except (OSError, ValueError, KeyError, json.JSONDecodeError):
            pass
        return {self.catalog.default_key}

    def _known(self, key: str) -> bool:
        try:
            self.catalog.get(key)
            return True
        except KeyError:
            return False

    def _write_state(self) -> None:
        self._state_path.write_text(
            json.dumps({"active_models": sorted(self._active_keys)}, indent=2),
            encoding="utf-8",
        )

    def _model_state_path(self, key: str) -> Path:
        return self.runtime_root / key / "installation.json"

    @staticmethod
    def _install_requirements(
        requirements: tuple[str, ...], target: Path, *, progress=None, cancellation=None
    ) -> None:
        command = [
            sys.executable,
            "-m",
            "pip",
            "install",
            "--disable-pip-version-check",
            "--progress-bar",
            "off",
            "--retries",
            "8",
            "--timeout",
            "30",
            "--target",
            str(target),
            *requirements,
        ]
        process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        output: list[str] = []
        assert process.stdout is not None
        for line in process.stdout:
            text = line.strip()
            if text:
                output.append(text)
                if callable(progress):
                    progress(1, 4, text[-500:])
            if callable(cancellation) and cancellation():
                process.terminate()
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()
                raise InterruptedError("Model installation cancelled")
        return_code = process.wait()
        if return_code != 0:
            raise RuntimeError("\n".join(output[-30:]) or "pip dependency installation failed")

    def _restore_active_capabilities(self) -> None:
        replace = getattr(self._capability_router, "replace", None)
        if not callable(replace):
            return
        for key in sorted(self._active_keys):
            spec = self.catalog.get(key)
            if spec.built_in or not self.is_installed(key):
                continue
            try:
                instance = self.instantiate(key)
                if getattr(instance, "descriptor", None) is not None:
                    replace(instance, active=True)
            except Exception:
                # An installed marker never makes startup dependent on an optional model.
                continue

    def _capability_id(self, key: str) -> str | None:
        resident = self._loaded.get(key)
        if resident is None:
            return None
        descriptor = getattr(resident.instance, "descriptor", None)
        value = getattr(descriptor, "capability_id", None)
        return str(value) if value else None

    @staticmethod
    def _artifact_checksums(instance: object) -> dict[str, str]:
        paths = getattr(instance, "artifact_paths", None)
        if not callable(paths):
            return {}
        checksums: dict[str, str] = {}
        for index, root in enumerate(paths()):
            path = Path(root)
            files = (path,) if path.is_file() else tuple(sorted(path.rglob("*")))
            for file_path in files:
                if not file_path.is_file():
                    continue
                digest = hashlib.sha256()
                with file_path.open("rb") as handle:
                    for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                        digest.update(chunk)
                relative = Path(file_path.name) if path.is_file() else file_path.relative_to(path)
                checksums[f"{index}:{relative.as_posix()}"] = digest.hexdigest()
        return checksums

    def _dependency_dir(self, key: str) -> Path:
        return self.runtime_root / key / "site-packages"

    @staticmethod
    def _configure_instance(instance: object, artifact_root: Path, dependency_root: Path) -> None:
        configure_runtime = getattr(instance, "configure_runtime", None)
        if not callable(configure_runtime):
            return
        if "dependency_root" in inspect.signature(configure_runtime).parameters:
            configure_runtime(artifact_root, dependency_root=dependency_root)
        else:
            configure_runtime(artifact_root)

    def _enable_dependency_path(self, key: str) -> None:
        path = str(self._dependency_dir(key))
        if Path(path).is_dir() and path not in sys.path:
            sys.path.insert(0, path)

    @staticmethod
    def _clear_torch_cache() -> None:
        try:
            import torch

            if torch.cuda.is_available():
                torch.cuda.synchronize()
                torch.cuda.empty_cache()
                ipc_collect = getattr(torch.cuda, "ipc_collect", None)
                if callable(ipc_collect):
                    ipc_collect()
        except (ImportError, RuntimeError):
            pass
