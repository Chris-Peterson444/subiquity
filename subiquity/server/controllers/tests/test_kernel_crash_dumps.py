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

import jsonschema
from jsonschema.validators import validator_for

from subiquity.server.controllers.kernel_crash_dumps import KernelCrashDumpsController
from subiquitycore.tests import SubiTestCase
from subiquitycore.tests.parameterized import parameterized


class TestKernelCrashDumpsSchema(SubiTestCase):
    def test_valid_schema(self):
        """Test that the expected autoinstall JSON schema is valid"""

        JsonValidator: jsonschema.protocols.Validator = validator_for(
            KernelCrashDumpsController.autoinstall_schema
        )

        JsonValidator.check_schema(KernelCrashDumpsController.autoinstall_schema)

    @parameterized.expand(
        (
            # (config, valid)
            # Valid configs
            ({"enabled": True}, True),
            ({"enabled": True, "crashkernel": ""}, True),
            ({"enabled": True, "memory-min": "", "memory-reserved": ""}, True),
            # Invalid configs
            ({"crashkernel": ""}, False),
            ({"memory-min": "", "memory-reserved": ""}, False),
            (
                {
                    "enabled": True,
                    "crashkernel": "",
                    "memory-min": "",
                    "memory-reserved": "",
                },
                False,
            ),
        )
    )
    def test_valid_configs(self, config, valid):
        """Test expected good configs against schema"""

        if valid:
            jsonschema.validate(config, KernelCrashDumpsController.autoinstall_schema)
        else:
            with self.assertRaises(jsonschema.ValidationError):

                jsonschema.validate(
                    config, KernelCrashDumpsController.autoinstall_schema
                )
