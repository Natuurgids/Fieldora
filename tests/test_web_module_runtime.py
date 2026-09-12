from __future__ import annotations

from dataclasses import dataclass, field

import pytest

from natureai_next.server.web_module_contracts import WebModuleRegistry, WebModuleSpec
from natureai_next.server.web_module_runtime import (
    WebModuleRuntime,
    WebModuleRuntimeError,
    WebModuleState,
)


@dataclass
class RecordingAdapter:
    events: list[str] = field(default_factory=list)
    fail_mount: bool = False
    fail_unmount: bool = False

    def mount(self, spec: WebModuleSpec) -> None:
        self.events.append(f"mount:{spec.module_id}")
        if self.fail_mount:
            raise RuntimeError("mount exploded")

    def unmount(self, spec: WebModuleSpec) -> None:
        self.events.append(f"unmount:{spec.module_id}")
        if self.fail_unmount:
            raise RuntimeError("unmount exploded")


def _registry() -> WebModuleRegistry:
    return WebModuleRegistry(
        (
            WebModuleSpec("projects.core", "/projects", "Projects"),
            WebModuleSpec(
                "portfolio",
                "/portfolio",
                "Portfolio",
                dependencies=("projects.core",),
            ),
        )
    )


def test_route_activation_unmounts_previous_module_before_mounting_next() -> None:
    registry = _registry()
    runtime = WebModuleRuntime(registry)
    projects = RecordingAdapter()
    portfolio = RecordingAdapter()
    runtime.bind("projects.core", projects)
    runtime.bind("portfolio", portfolio)

    runtime.activate_route("/projects")
    runtime.activate_route("/portfolio?view=summary")

    assert projects.events == ["mount:projects.core", "unmount:projects.core"]
    assert portfolio.events == ["mount:portfolio"]
    assert runtime.snapshot("projects.core").state is WebModuleState.UNMOUNTED
    assert runtime.snapshot("portfolio").state is WebModuleState.MOUNTED
    assert runtime.active_module_id == "portfolio"


def test_dependency_must_be_bound_before_dependent_module_can_activate() -> None:
    runtime = WebModuleRuntime(_registry())
    runtime.bind("portfolio", RecordingAdapter())

    with pytest.raises(WebModuleRuntimeError, match="dependency 'projects.core'"):
        runtime.activate("portfolio")


def test_mount_failure_is_isolated_and_recorded() -> None:
    runtime = WebModuleRuntime(_registry())
    runtime.bind("projects.core", RecordingAdapter(fail_mount=True))

    with pytest.raises(WebModuleRuntimeError, match="mount failed"):
        runtime.activate("projects.core")

    snapshot = runtime.snapshot("projects.core")
    assert snapshot.state is WebModuleState.FAILED
    assert snapshot.error == "mount exploded"
    assert runtime.active_module_id is None


def test_duplicate_adapter_binding_is_rejected() -> None:
    runtime = WebModuleRuntime(_registry())
    runtime.bind("projects.core", RecordingAdapter())

    with pytest.raises(WebModuleRuntimeError, match="already has an adapter"):
        runtime.bind("projects.core", RecordingAdapter())


def test_unknown_route_does_not_change_active_module() -> None:
    runtime = WebModuleRuntime(_registry())
    runtime.bind("projects.core", RecordingAdapter())
    runtime.activate("projects.core")

    with pytest.raises(WebModuleRuntimeError, match="no module owns route"):
        runtime.activate_route("/not-a-module")

    assert runtime.active_module_id == "projects.core"
    assert runtime.snapshot("projects.core").state is WebModuleState.MOUNTED
