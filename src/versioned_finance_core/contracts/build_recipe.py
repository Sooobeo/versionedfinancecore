"""Versioned, data-only instructions for offline case review builds."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

BUILD_RECIPE_VERSION = 1
BUILD_STEPS = frozenset({
    "core_cash", "conditional_valuation", "guidance_comparison",
    "dfs_reproduction", "credit_evidence", "capital_evidence",
})
STEP_MODULES = {
    "conditional_valuation": "M1", "guidance_comparison": "M1",
    "dfs_reproduction": "M2", "credit_evidence": "M3",
    "capital_evidence": "M2",
}


@dataclass(frozen=True)
class BuildRecipe:
    steps: tuple[str, ...]
    scope_limitations: tuple[str, ...]

    @classmethod
    def from_mapping(cls, data: Mapping[str, object]) -> BuildRecipe:
        if not isinstance(data, Mapping):
            raise ValueError("build recipe must be a JSON object")  # noqa: TRY004
        if set(data) != {"schema_version", "steps", "scope_limitations"}:
            raise ValueError("build recipe fields must be schema_version, steps, scope_limitations")
        if type(data["schema_version"]) is not int or data["schema_version"] != BUILD_RECIPE_VERSION:
            raise ValueError("Unsupported build recipe schema_version")
        steps = data["steps"]
        limitations = data["scope_limitations"]
        for label, items in (("steps", steps), ("scope_limitations", limitations)):
            if not isinstance(items, list) or any(
                not isinstance(item, str) or not item.strip() or item != item.strip()
                for item in items
            ):
                raise ValueError(f"build recipe {label} must be a list of nonempty strings")
            if len(items) != len(set(items)):
                raise ValueError(f"Duplicate build recipe {label}")
        if unknown := set(steps) - BUILD_STEPS:
            raise ValueError(f"Unknown build steps: {sorted(unknown)}")
        for step in ("conditional_valuation", "credit_evidence"):
            if step in steps and ("core_cash" not in steps or steps.index("core_cash") > steps.index(step)):
                raise ValueError(f"{step} requires core_cash first")
        return cls(tuple(steps), tuple(limitations))

    def validate_modules(self, modules: tuple[str, ...]) -> None:
        for step in self.steps:
            if step in STEP_MODULES and STEP_MODULES[step] not in modules:
                raise ValueError(f"Build step {step} requires active module {STEP_MODULES[step]}")
