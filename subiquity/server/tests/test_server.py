# Copyright 2022 Canonical, Ltd.
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

import os
import shlex
from unittest.mock import Mock, patch

import jsonschema
from jsonschema.validators import validator_for

from subiquity.common.types import PasswordKind
from subiquity.server.autoinstall import AutoinstallValidationError
from subiquity.server.server import (
    MetaController,
    SubiquityServer,
    cloud_autoinstall_path,
    iso_autoinstall_path,
    root_autoinstall_path,
)
from subiquitycore.tests import SubiTestCase
from subiquitycore.tests.mocks import make_app
from subiquitycore.utils import run_command


class TestAutoinstallLoad(SubiTestCase):
    async def asyncSetUp(self):
        self.tempdir = self.tmp_dir()
        os.makedirs(self.tempdir + "/cdrom", exist_ok=True)
        opts = Mock()
        opts.dry_run = True
        opts.output_base = self.tempdir
        opts.machine_config = "examples/machines/simple.json"
        opts.kernel_cmdline = {}
        opts.autoinstall = None
        self.server = SubiquityServer(opts, None)
        self.server.base_model = Mock()
        self.server.base_model.root = opts.output_base

    def path(self, relative_path):
        return self.tmp_path(relative_path, dir=self.tempdir)

    def create(self, path, contents):
        path = self.path(path)
        with open(path, "w") as fp:
            fp.write(contents)
        return path

    def test_autoinstall_disabled(self):
        self.server.opts.autoinstall = ""
        self.server.kernel_cmdline = {"subiquity.autoinstallpath": "kernel"}
        self.create(root_autoinstall_path, "root")
        self.create(cloud_autoinstall_path, "cloud")
        self.create(iso_autoinstall_path, "iso")
        self.assertIsNone(self.server.select_autoinstall())

    def test_arg_wins(self):
        arg = self.create(self.path("arg.autoinstall.yaml"), "arg")
        self.server.opts.autoinstall = arg
        kernel = self.create(self.path("kernel.autoinstall.yaml"), "kernel")
        self.server.kernel_cmdline = {"subiquity.autoinstallpath": kernel}
        root = self.create(root_autoinstall_path, "root")
        self.create(cloud_autoinstall_path, "cloud")
        self.create(iso_autoinstall_path, "iso")
        self.assertEqual(root, self.server.select_autoinstall())
        self.assert_contents(root, "arg")

    def test_kernel_wins(self):
        self.server.opts.autoinstall = None
        kernel = self.create(self.path("kernel.autoinstall.yaml"), "kernel")
        self.server.kernel_cmdline = {"subiquity.autoinstallpath": kernel}
        root = self.create(root_autoinstall_path, "root")
        self.create(cloud_autoinstall_path, "cloud")
        self.create(iso_autoinstall_path, "iso")
        self.assertEqual(root, self.server.select_autoinstall())
        self.assert_contents(root, "kernel")

    def test_root_wins(self):
        self.server.opts.autoinstall = None
        self.server.kernel_cmdline = {}
        root = self.create(root_autoinstall_path, "root")
        self.create(cloud_autoinstall_path, "cloud")
        self.create(iso_autoinstall_path, "iso")
        self.assertEqual(root, self.server.select_autoinstall())
        self.assert_contents(root, "root")

    def test_cloud_wins(self):
        self.server.opts.autoinstall = None
        self.server.kernel_cmdline = {}
        root = self.path(root_autoinstall_path)
        self.create(cloud_autoinstall_path, "cloud")
        self.create(iso_autoinstall_path, "iso")
        self.assertEqual(root, self.server.select_autoinstall())
        self.assert_contents(root, "cloud")

    def test_iso_wins(self):
        self.server.opts.autoinstall = None
        self.server.kernel_cmdline = {}
        root = self.path(root_autoinstall_path)
        # No cloud config file
        self.create(iso_autoinstall_path, "iso")
        self.assertEqual(root, self.server.select_autoinstall())
        self.assert_contents(root, "iso")

    def test_nobody_wins(self):
        self.assertIsNone(self.server.select_autoinstall())

    def test_bogus_autoinstall_argument(self):
        self.server.opts.autoinstall = self.path("nonexistant.yaml")
        with self.assertRaises(Exception):
            self.server.select_autoinstall()

    # Only care about changes to autoinstall, not validity
    @patch("subiquity.server.server.SubiquityServer.validate_autoinstall")
    def test_early_commands_changes_autoinstall(self, mocked_validator):
        self.server.controllers = Mock()
        self.server.controllers.instances = []
        rootpath = self.path(root_autoinstall_path)

        cmd = f"sed -i -e '$ a stuff: things' {rootpath}"
        contents = f"""\
version: 1
early-commands: ["{cmd}"]
"""
        arg = self.create(self.path("arg.autoinstall.yaml"), contents)
        self.server.opts.autoinstall = arg

        self.server.autoinstall = self.server.select_autoinstall()
        self.server.load_autoinstall_config(only_early=True)
        before_early = {"version": 1, "early-commands": [cmd]}
        self.assertEqual(before_early, self.server.autoinstall_config)
        run_command(shlex.split(cmd), check=True)

        self.server.load_autoinstall_config(only_early=False)
        after_early = {"version": 1, "early-commands": [cmd], "stuff": "things"}
        self.assertEqual(after_early, self.server.autoinstall_config)


class TestAutoinstallValidation(SubiTestCase):
    async def asyncSetUp(self):
        opts = Mock()
        opts.dry_run = True
        opts.output_base = self.tmp_dir()
        opts.machine_config = "examples/machines/simple.json"
        self.server = SubiquityServer(opts, None)
        self.server.base_schema = {
            "type": "object",
            "properties": {
                "some-key": {
                    "type": "boolean",
                },
            },
        }
        self.server.make_apport_report = Mock()

    # Pseudo Load controllers to avoid patching loading logic for each controller
    # Only need to access class attributes
    def pseudo_load_controllers(self):
        controller_classes = []
        for prefix in self.server.controllers.controller_names:
            controller_classes.append(
                self.server.controllers._get_controller_class(prefix)
            )

        self.server.controllers.instances = controller_classes

    def test_valid_schema(self):
        """Test that the expected autoinstall JSON schema is valid"""

        JsonValidator: jsonschema.protocols.Validator = validator_for(
            SubiquityServer.base_schema
        )

        JsonValidator.check_schema(SubiquityServer.base_schema)

    def test_autoinstall_validation__error_type(self):
        """Test that bad autoinstall data throws AutoinstallValidationError"""

        bad_ai_data = {"some-key": "not a bool"}
        self.server.autoinstall_config = bad_ai_data

        with self.assertRaises(AutoinstallValidationError):
            self.server.validate_autoinstall()

    async def test_autoinstall_validation__no_error_report(self):
        """Test no apport reporting"""

        exception = AutoinstallValidationError("Mock")

        loop = Mock()
        context = {"exception": exception}

        with patch("subiquity.server.server.log"):
            with patch.object(self.server, "_run_error_cmds"):
                self.server._exception_handler(loop, context)

        self.server.make_apport_report.assert_not_called()

    @patch("subiquity.server.server.log")
    def test_autoinstall_validation__enforce_top_level_keys(self, log_mock):
        """Test strict top level keys"""

        # Reset base schema
        self.server.base_schema = SubiquityServer.base_schema

        # "apt" should be known by the MirrorController and not considered
        # by the server's validation
        bad_ai_data = {
            "version": 1,
            "apt": "Invalid but deferred",
            "literally-anything": "lmao",
        }

        self.server.autoinstall_config = bad_ai_data

        # Load the controllers
        self.pseudo_load_controllers()

        # OK in Version 1 but ensure warnings
        self.server.validate_autoinstall()
        log_mock.warning.assert_called()

        # Not OK in Versions >=2
        bad_ai_data["version"] = 2
        self.server.autoinstall_config = bad_ai_data

        log_mock.reset()

        with self.assertRaises(AutoinstallValidationError) as ctx:
            self.server.validate_autoinstall()

        exception = ctx.exception

        self.assertIn("literally-anything", str(exception))
        self.assertNotIn("apt", str(exception))

        log_mock.error.assert_called()

    def test_autoinstall__strip_controller_keys(self):
        """Test only controller keys are stripped"""

        # Mixed data: Has base sections, controller section, and a bad key
        autoinstall_config = {
            "version": 1,  # Should stay
            "interactive-sections": ["identity"],  # Should stay
            "apt": "...",  # Should be stripped
            "invalid_key": "...",  # Should stay
        }

        # Load the controllers
        self.pseudo_load_controllers()

        result = self.server._strip_controller_keys(autoinstall_config)

        self.assertIn("version", result)
        self.assertIn("interactive-sections", result)
        self.assertNotIn("apt", result)
        self.assertIn("invalid_key", result)


class TestMetaController(SubiTestCase):
    async def test_interactive_sections_not_present(self):
        mc = MetaController(make_app())
        mc.app.autoinstall_config = None
        self.assertIsNone(await mc.interactive_sections_GET())

    async def test_interactive_sections_empty(self):
        mc = MetaController(make_app())
        mc.app.autoinstall_config["interactive-sections"] = []
        self.assertEqual([], await mc.interactive_sections_GET())

    async def test_interactive_sections_all(self):
        mc = MetaController(make_app())
        mc.app.autoinstall_config["interactive-sections"] = ["*"]
        mc.app.controllers.instances = [
            Mock(autoinstall_key="f", interactive=Mock(return_value=False)),
            Mock(autoinstall_key=None, interactive=Mock(return_value=True)),
            Mock(autoinstall_key="t", interactive=Mock(return_value=True)),
        ]
        self.assertEqual(["t"], await mc.interactive_sections_GET())

    async def test_interactive_sections_one(self):
        mc = MetaController(make_app())
        mc.app.autoinstall_config["interactive-sections"] = ["network"]
        self.assertEqual(["network"], await mc.interactive_sections_GET())


class TestDefaultUser(SubiTestCase):
    @patch(
        "subiquity.server.server.user_key_fingerprints",
        Mock(side_effect=Exception("should not be called")),
    )
    async def test_no_default_user(self):
        opts = Mock()
        opts.dry_run = True
        opts.output_base = self.tmp_dir()
        opts.machine_config = "examples/machines/simple.json"
        server = SubiquityServer(opts, None)
        server._user_has_password = Mock(side_effect=Exception("should not be called"))

        opts.dry_run = False  # exciting!
        server.set_installer_password()
        self.assertIsNone(server.installer_user_name)
        self.assertEqual(PasswordKind.NONE, server.installer_user_passwd_kind)
