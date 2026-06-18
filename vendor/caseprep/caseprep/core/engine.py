"""CasePrep core engine facade.

The build facade is intentionally core-only: all transports now execute the
procedure-first deterministic builder directly.
"""

from __future__ import annotations

import inspect
import os
from dataclasses import replace
from typing import Awaitable, Callable, Mapping

from .contracts import BuildCasePlanRequest, BuildCasePlanResult, CoreMode
from .errors import CasePrepConfigurationError

VALID_CORE_MODES: set[str] = {"core"}

CoreBuildCasePlan = Callable[
    [BuildCasePlanRequest],
    BuildCasePlanResult | Awaitable[BuildCasePlanResult],
]


def resolve_core_mode(env: Mapping[str, str] | None = None) -> CoreMode:
    values = env if env is not None else os.environ
    raw_mode = values.get("CASEPREP_CORE_MODE", "core").strip().lower()
    mode = raw_mode or "core"
    if mode != "core":
        raise CasePrepConfigurationError(
            "CASEPREP_CORE_MODE only supports core",
            details={"field": "CASEPREP_CORE_MODE", "value": raw_mode},
        )
    return "core"


async def _maybe_await(value):
    if inspect.isawaitable(value):
        return await value
    return value


async def _default_core_build_caseplan(
    request: BuildCasePlanRequest,
) -> BuildCasePlanResult:
    from caseprep.core.builder import build_core_case_plan

    return await build_core_case_plan(request)


class CasePlanBuilder:
    """Facade for building case plans through the core pipeline."""

    def __init__(
        self,
        *,
        mode: CoreMode | None = None,
        core_builder: CoreBuildCasePlan | None = None,
        env: Mapping[str, str] | None = None,
    ) -> None:
        self.mode = mode or resolve_core_mode(env)
        if self.mode != "core":
            raise CasePrepConfigurationError(
                "mode must be core",
                details={"field": "mode", "value": self.mode},
            )
        self._core_builder = core_builder or _default_core_build_caseplan

    async def build_case_plan(
        self,
        request: BuildCasePlanRequest,
    ) -> BuildCasePlanResult:
        raw_result = await _maybe_await(self._core_builder(request))
        return self._coerce_result(raw_result, request)

    @staticmethod
    def _coerce_result(
        raw_result: BuildCasePlanResult,
        request: BuildCasePlanRequest,
    ) -> BuildCasePlanResult:
        topic = raw_result.topic or request.resolved_case_input()
        return replace(raw_result, topic=topic, mode="core")
