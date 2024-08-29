# Copyright 2024 Canonical, Ltd.
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, version 3.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

import logging
from typing import TypedDict

from subiquity.server.controller import NonInteractiveController

log = logging.getLogger("subiquity.server.controllers.kernel_crash_dumps")

KernelCrashDumpsConfig = TypedDict(
    "KernelCrashDumpsConfig",
    {
        "enabled": bool,
        "memory-min": str,
        "memory-reserved": str,
        "crashkernel": str,
    },
    total=False,
)


class KernelCrashDumpsController(NonInteractiveController):
    model_name = "kernel_crash_dumps"
    autoinstall_key = "kernel-crash-dumps"
    autoinstall_schema = {
        "type": "object",
        "properties": {
            "enabled": {"type": "boolean"},
            "memory-min": {"type": "string"},
            "memory-reserved": {"type": "string"},
            "crashkernel": {"type": "string"},
        },
        "required": ["enabled"],
        "oneOf": [
            {
                "required": ["memory-min", "memory-reserved"],
                "not": {"required": ["crashkernel"]},
            },
            {
                "allOf": [
                    {"not": {"required": ["memory-min"]}},
                    {"not": {"required": ["memory-reserved"]}},
                ]
            },
        ],
        "additionalProperties": False,
    }

    def load_autoinstall_data(self, data: KernelCrashDumpsConfig | None) -> None:
        if data is None:
            log.debug("Letting curtin decide if kernel crash dumps should be enabled")
            return
        self.model.enabled = data["enabled"]
        self.model.memory_min = data.get("memory-min")
        self.model.memory_reserved = data.get("memory-reserved")
        self.model.crashkernel = data.get("crashkernel")

    def make_autoinstall(self) -> dict[str, str]:
        # Automatic determination implies no autoinstall
        if self.model.enabled is None:
            return {}

        rv = {"enabled": self.model.enabled}
        if self.crashkernel:
            rv["crashkernel"] = self.model.crashkernel
        else:
            rv |= {
                "memory-min": self.model.memory_min,
                "memory-reserved": self.model.memory_reserved,
            }

        return rv
