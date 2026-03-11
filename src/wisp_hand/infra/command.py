from __future__ import annotations

import subprocess
from dataclasses import dataclass


@dataclass(slots=True)
class CommandResult:
    args: list[str]
    stdout: str
    stderr: str
    returncode: int


class CommandRunner:
    def __call__(self, args: list[str]) -> CommandResult:
        completed = subprocess.run(
            args,
            capture_output=True,
            text=True,
            check=False,
        )
        return CommandResult(
            args=args,
            stdout=completed.stdout,
            stderr=completed.stderr,
            returncode=completed.returncode,
        )
