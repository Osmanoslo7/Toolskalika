"""Collected validation results. Errors block rendering; warnings are shown and do not."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Report:
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    checked: int = 0

    @property
    def ok(self) -> bool:
        return not self.errors

    def error(self, message: str) -> None:
        self.errors.append(message)

    def warn(self, message: str) -> None:
        self.warnings.append(message)

    def issue(self, approved: bool, message: str) -> None:
        """Approved assets must be complete (error). Drafts may still be in progress (warning)."""
        if approved:
            self.error(message)
        else:
            self.warn(message)
