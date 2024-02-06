# Copyright 2024 Canonical, Ltd.
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as
# published by the Free Software Foundation, either version 3 of the
# License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
import logging
from typing import Optional

log = logging.getLogger("subiquity.server.autoinstall")


class AutoinstallError(Exception):
    pass


class AutoinstallValidationError(AutoinstallError):
    def __init__(
        self,
        section: str,
        message: Optional[str] = None,
    ):
        if not message:
            self.message: str = f"Malformed autoinstall in {section!r} section"
        else:
            self.message: str = message

        self.section: str = section
        super().__init__(self.message)
