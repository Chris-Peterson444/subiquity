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

log = logging.getLogger("subiquity.models.kernel_crash_dumps")


class KernelCrashDumpsModel:
    # Set to True/False via autoinstall. Defaults to None to let curtin decide
    # based on release, requirements, etc.
    enabled: bool | None = None

    # memory_min and memory_reserved are combined to generate simple crashkernel
    # by curtin (i.e. crashkernel=memory_min:memory_reserved). Mutually
    # exclusive with crashkernel.
    memory_min: str | None = None
    memory_reserved: str | None = None

    # Specific crashkernel a user can specify. Mutually exclusive with
    # memory_min and memory_reserved.
    crashkernel: str | None = None

    def render(self) -> dict[str, str]:
        if self.enabled is None:
            # Return "enabled: None" to allow curtin disambiguate whether it's
            # a subiquity install or a MAAS install. Probably rip this out when
            # MAAS is ready.
            return {"kernel-crash-dumps": {"enabled": None}}

        return {
            "kernel-crash-dumps": {
                "enabled": self.enabled,
                "memory-min": self.memory_min,
                "memory-reserved": self.memory_reserved,
                "crashkernel": self.crashkernel,
            },
        }
