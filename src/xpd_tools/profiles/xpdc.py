"""XPD-D Bluesky profile for the 28-ID-2 beamline at NSLS-II."""

import os

from xpd_tools.motors import fs

HTTP_API_KEY: str = os.environ.get(
    "QSERVER_HTTP_SERVER_API_KEY",
    ""
)
HTTP_SERVER_URI: str = os.environ.get(
    "QSERVER_HTTP_URI",
    "https://xf28id2-xpd-qs1.nsls2.bnl.gov",
)
OPHYD_ASYNC_PRESERVE_DETECTOR_STATE: str = os.environ.get(
    "OPHYD_ASYNC_PRESERVE_DETECTOR_STATE",
    "YES")
TILED_PROFILE: str = os.environ.get(
    "TILED_PROFILE",
    "xpd"
)
TILED_URI: str = os.environ.get(
    "TILED_URI",
    "https://tiled.nsls2.bnl.gov"
)
REDIS_HOST: str = os.environ.get(
    "REDIS_HOST",
    "xf28id2-xpdd-redis1.nsls2.bnl.gov"
)
ZMQ_CONSUMER_ADDR: str = os.environ.get(
    "ZMQ_CONSUMER_ADDR",
    "ipc:///var/lib/bluesky-zmq-proxy/xpd-ipc-in-ipc-out/out.sock",
)

# =================================================================
# Set Up Motors
# =================================================================


fs = fs
