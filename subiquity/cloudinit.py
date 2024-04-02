"""Shared cloudinit utility functions"""

import asyncio
import json
import logging
import re
from collections.abc import Awaitable
from subprocess import CompletedProcess
from typing import Any, Optional

from subiquity.server.nonreportable import NonReportableException
from subiquitycore.utils import arun_command, run_command

log = logging.getLogger("subiquity.cloudinit")


class CloudInitSchemaValidationError(NonReportableException):
    """Exception for cloud config schema validation failure.

    Attributes:
        keys -- List of keys which are the cause of the failure
    """

    def __init__(
        self,
        keys: list[str],
        message: str = "Cloud config schema failed to validate.",
    ) -> None:
        super().__init__(message)
        self.keys = keys


def get_host_combined_cloud_config() -> dict:
    """Return the host system /run/cloud-init/combined-cloud-config.json"""
    try:
        with open("/run/cloud-init/combined-cloud-config.json") as fp:
            config = json.load(fp)
            log.debug(
                "Loaded cloud config from /run/cloud-init/combined-cloud-config.json"
            )
            return config
    except FileNotFoundError:
        log.debug(
            "Failed to load combined-cloud-config, file not found. "
            "This is expected for cloud-init <= v23.2.1."
        )
        return {}
    except (IOError, OSError, AttributeError, json.decoder.JSONDecodeError) as ex:
        log.debug("Failed to load combined-cloud-config: %s", ex)
        return {}


def cloud_init_version() -> str:
    # looks like 24.1~3gb729a4c4-0ubuntu1
    cmd = ["dpkg-query", "-W", "-f=${Version}", "cloud-init"]
    sp = run_command(cmd, check=False)
    version = re.split("[-~]", sp.stdout)[0]
    log.debug(f"cloud-init version: {version}")
    return version


def supports_format_json() -> bool:
    return cloud_init_version() >= "22.4"


def supports_recoverable_errors() -> bool:
    return cloud_init_version() >= "23.4"


def read_json_extended_status(stream):
    try:
        status = json.loads(stream)
    except json.JSONDecodeError:
        return None

    return status.get("extended_status", status.get("status", None))


def read_legacy_status(stream):
    for line in stream.splitlines():
        if line.startswith("status:"):
            try:
                return line.split()[1]
            except IndexError:
                pass
    return None


def read_recoverable_errors(
    stream: bytes | str,
    level: Optional[str] = None,
) -> list[str]:
    """Retrieve recoverable errors from cloud-init status."""

    try:
        status: dict[str, Any] = json.loads(stream)
    except json.JSONDecodeError:
        log.warning("Failed to decode cloud-init status output")
        return []

    errors_by_level: dict[str, list[str]] = status.get("recoverable_errors", {})

    if level is not None:
        return errors_by_level.get(level, [])

    all_errors: list[str] = []
    for _level in errors_by_level:
        all_errors.extend(errors_by_level[_level])

    return all_errors


async def get_schema_failure_sources() -> list[str]:
    """Retrieve the keys causing schema failure."""

    cmd: list[str] = ["cloud-init", "schema", "--system"]
    status_coro: Awaitable = arun_command(cmd, clean_locale=True)
    try:
        sp: CompletedProcess = await asyncio.wait_for(status_coro, 10)
    except asyncio.TimeoutError:
        log.warning("cloud-init schema --system timed out")
        return []

    error: str = sp.stderr  # Relies on arun_command decoding to utf-8 str by default

    # Matches:
    # ('some-key' was unexpected)
    # ('some-key', 'another-key' were unexpected)
    pattern = r"\((?P<args>'[\w\-]+'(,\s'[\w\-]+')*)+ (?:was|were) unexpected\)"
    search_result = re.search(pattern, error)

    if search_result is None:
        return []

    args_list: list[str] = search_result.group("args").split(", ")
    no_quotes: list[str] = [arg.strip("'") for arg in args_list]

    return no_quotes


async def cloud_init_status_wait() -> (bool, Optional[str]):
    """Wait for cloud-init completion, and return if timeout ocurred and best
    available status information.
    :return: tuple of (ok, status string or None)
    """
    cmd = ["cloud-init", "status", "--wait"]
    if format_json := supports_format_json():
        cmd += ["--format=json"]
    status_coro = arun_command(cmd)
    try:
        sp = await asyncio.wait_for(status_coro, 600)
    except asyncio.TimeoutError:
        return (False, "timeout")

    if format_json:
        status = read_json_extended_status(sp.stdout)
    else:
        status = read_legacy_status(sp.stdout)
    return (True, status)


async def validate_cloud_init_schema() -> None:
    """Check for cloud-init schema errors.
    Returns (None) if the cloud-config schmea validated OK according to
    cloud-init. Otherwise, a CloudInitSchemaValidationError is thrown
    which contains a list of the keys which failed to validate.
    Requires cloud-init supporting recoverable errors and extended status.

    :return: None if cloud-init schema validated succesfully.
    :rtype: None
    :raises CloudInitSchemaValidationError: If cloud-init schema did not validate
            succesfully.
    """
    causes: list[str] = await get_schema_failure_sources()

    if causes:
        raise CloudInitSchemaValidationError(keys=causes)

    return None
