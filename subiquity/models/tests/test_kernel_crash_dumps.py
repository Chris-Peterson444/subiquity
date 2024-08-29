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

from subiquity.models.kernel_crash_dumps import KernelCrashDumpsModel
from subiquitycore.tests import SubiTestCase


class TestKernelCrashDumpsModel(SubiTestCase):
    def setUp(self):
        self.model = KernelCrashDumpsModel()

    def test_automatic_decision(self):
        """Test the curtin config for curtin automatic enable."""
        expected = {"kernel-crash-dumps": {"enabled": None}}
        self.assertEqual(expected, self.model.render())

    def test_render_formatting(self):
        """Test the curtin config formatting.

        We allow the None type in the curtin config, so this is mostly just
        to test the config gets populated correctly.
        """

        config = {}
        self.model.enabled = config["enabled"] = True
        self.model.crashkernel = config["crashkernel"] = "4G:512M"
        # Also including these isn't really a valid config, but the model
        # doesn't do validation.
        self.model.memory_min = config["memory-min"] = "4G"
        self.model.memory_reserved = config["memory-reserved"] = "512M"
        expected = {"kernel-crash-dumps": config}
        self.assertEqual(expected, self.model.render())
