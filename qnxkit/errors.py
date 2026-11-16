"""Shared error / issue types for qnxkit."""

from __future__ import annotations

from dataclasses import dataclass, field


class QnxKitError(Exception):
    """A user-facing qnxkit failure (bad input, malformed file, ...)."""


@dataclass
class Issue:
    """One finding from a check: error, warning or informational note."""

    level: str  # "error" | "warning" | "info"
    code: str
    message: str
    file: str = ""
    line: int = 0
    suggestion: str = ""

    def __str__(self) -> str:
        loc = self.file
        if self.line:
            loc += f":{self.line}"
        out = f"{self.level.upper()}: {loc}: [{self.code}] {self.message}" if loc else (
            f"{self.level.upper()}: [{self.code}] {self.message}"
        )
        if self.suggestion:
            out += f"  -> {self.suggestion}"
        return out


@dataclass
class CheckResult:
    """The outcome of one check (buildfile, toolchain, analyze, ifs)."""

    ok: bool = True
    issues: list = field(default_factory=list)
    summary: dict = field(default_factory=dict)

    @property
    def errors(self) -> list:
        return [i for i in self.issues if i.level == "error"]

    @property
    def warnings(self) -> list:
        return [i for i in self.issues if i.level == "warning"]

    def add(self, level: str, code: str, message: str, file: str = "",
            line: int = 0, suggestion: str = "") -> None:
        self.issues.append(Issue(level, code, message, file, line, suggestion))
        if level == "error":
            self.ok = False
