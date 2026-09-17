"""Simulated-device support for `BuildAgent.build_local()`.

Kept separate from the rest of `optimization` on purpose: everything else
in this package is hardware-agnostic (JSON-serializable config, no real
device objects) so it can round-trip through `to_config()`/`from_config()`
and run against a Queue Server. This module is the opposite -- it builds
concrete (simulated) device objects, which only makes sense for the local,
no-queue-server `build_local()` path.

`xpd-profile-collection`, which historically owned the *real* device
definitions (real PV prefixes) for these same devices, is being
deprecated. These are simulated stand-ins for verifying that a `BuildAgent`
config actually builds and its acquisition plan actually runs -- not for
driving real hardware.
"""

from __future__ import annotations

from .devices import build_xpd_objects, identity_wrap_xray_run

__all__ = ["build_xpd_objects", "identity_wrap_xray_run"]
