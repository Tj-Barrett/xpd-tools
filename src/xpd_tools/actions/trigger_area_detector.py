"""Trigger an area detector."""

import uuid
from collections import ChainMap
from collections.abc import Sequence

import bluesky.plan_stubs as bps
import bluesky.preprocessors as bpp
import numpy as np
from bluesky.protocols import Readable
from bluesky.utils import MsgGenerator, short_uid
from ophyd import EpicsMotor
from xpdacq.xpdacq import periodic_dark


def _pre_plan(
    xpd_configuration: dict,
    dets: Sequence[Readable],
    exposure: float = 0.1,
    frame_acq_time: float = 0.1,
    ):
    """Handle detector exposure time + xpdan required metadata.

    Args:
        dets (list):
            list of detector ophyd object, e.g., [piatus1] or [pe1c]

        exposure (float, optional):
            total exposure (measurement) time in seconds.
            Defaults to 0.1.

        frame_acq_time (float, optional):
            Change frame acquistion time if needed, only for pe1c.
            Defaults to 0.1.

    Returns
    -------
        None

    Yields
    ------
        msg: Msg
    """
    try:
        xpd_configuration["area_det"] = dets[0]

    except (NameError, KeyError):
        pass

    # Change frame acquisition time (not using glbl)
    if (type(frame_acq_time) is float) or (type(frame_acq_time) is int):
        for det in dets:
            yield from bps.mv(det.cam.acquire_time, frame_acq_time)

    # setting up area_detector
    for ad in (d for d in dets if hasattr(d, "cam")):
        if hasattr(ad, 'number_of_sets'):
            yield from bps.mv(ad.number_of_sets, 1)

        """
        Perkin-Elmer detector acquisition must be off to change settings.
        (1) Turn acquisition off
        (2) Change acquisition settings
        (3) Turn acquisition on (continuous mode)

        Made sure there are sleeps to give enough time for roundtrip.
        """
        # Turn off
        yield from bps.mv(ad.cam.acquire, 0)
        # Change acquisition time
        yield from bps.mv(ad.cam.acquire_time, frame_acq_time)
        yield from bps.sleep(1)
        # Change acquisition period
        yield from bps.mv(ad.cam.acquire_period, frame_acq_time)
        yield from bps.sleep(1)
        # Determine and set number of frames
        num_frame = float(np.ceil(exposure / frame_acq_time))
        yield from bps.mv(ad.images_per_set, num_frame)
        yield from bps.sleep(0.5)
        # Determine and set acquisition time
        acq_time = yield from bps.rd(ad.cam.acquire_time)
        yield from bps.sleep(0.5)
        # Turn on
        yield from bps.mv(ad.cam.acquire, 1)
        yield from bps.sleep(1)

    for ad in (d for d in dets if hasattr(d, "driver")):
        if hasattr(ad, 'number_of_sets'):
            yield from bps.mv(ad.number_of_sets, 1)

        yield from bps.mv(ad.driver.acquire_time, exposure)
        yield from bps.mv(ad.driver.acquire_period, exposure)
        num_frame = yield from bps.rd(ad.driver.num_images)
        acq_time = yield from bps.rd(ad.driver.acquire_time)
        computed_exposure = num_frame * acq_time

    acq_time = float(acq_time)
    computed_exposure = float(computed_exposure)
    num_frame = int(num_frame)

    sp = {
        "time_per_frame": acq_time,
        "num_frames": num_frame,
        "requested_exposure": exposure,
        "computed_exposure": computed_exposure,
        "type": "generator",
        "uid": str(uuid.uuid4()),
        "plan_name": "bps.trigger",
    }

    _md = ChainMap(
        {
            "sp_time_per_frame": acq_time,
            "sp_num_frames": num_frame,
            "sp_requested_exposure": exposure,
            "sp_computed_exposure": computed_exposure,
            "sp_type": "bps.trigger",
            "sp_uid": str(uuid.uuid4()),
            "sp_plan_name": "trigger",
            "sp_detector": dets[0].name,
            "detectors": [area_det.name for area_det in dets],
            # "data_keys": "pe1c_image",
        },
    )

    # update md
    # _md.update({"sp": sp, **{f"sp_{k}": v for k, v in sp.items()}})
    _md.update({"sp": sp, })
    print(_md)

    return _md


def trigger_area_detector(
    dets: Sequence[Readable],
    fs_motor: EpicsMotor,
    exposure: float = 0.1,
    stream_name: str = "primary",
    md: dict | None = None,
    no_dark: bool = False,
    jogging: list | None = None,
    frame_acq_time: float = 0.1,
    user_config: dict | None = None,
    sample_y: EpicsMotor | None = None
    ):
    """Trigger the area det.

    Args:
        dets (list):
            list of detector ophyd object, e.g., [piatus1] or [pe1c]

        exposure (float, optional):
            total exposure (measurement) time in seconds.
            Defaults to 0.1.

        stream_name (str, optional):
            stream name in the event document, 'primary' is recommended.
            Defaults to 'primary'.

        md (dict, optional):
            additional metadata.
            e.g., md = {'note':'dummy test'}
            Defaults to None.

        no_dark (bool, optional):
            if no_dark = True, the dark scan will be skipped, especially for pilatus.
            Defaults to False.

        jogging (list, optional):
            If jogging, three elemetns needs to be defined as [jog_motor, start, stop].
            e.g.,  jogging = [OT_stage_2_X, 0.5, 3.7]
            Defaults to None.

        frame_acq_time (float, optional):
            Change frame acquistion time if needed, only for pe1c.
            Defaults to 0.1.

        user_config (dict, optional):
            Pass self-defined configuration info to pdfstream.
            e.g.,  user_config = {
                'auto_mask': False,
                'qmaxinst':28,
                'qmax':28.0,
                'rpoly':0.7,
                'user_mask': '/nsls2/auto-storage/pdf/pdfhack/legacy/processed/
                        xpdacq_data/user_data/config_base/Mask.npy',
                'method': 'splitpixel'
                }
            Defaults to None.

    Returns
    -------
        None

    Yields
    ------
        msg: Msg
    """
    if md is None:
        _md = {}
    else:
        _md = md

    sp_md: ChainMap = yield from _pre_plan(
        dets,
        exposure,
        frame_acq_time=frame_acq_time
    )
    sp_md["sp_plan_name"] = "trigger_areaDet",
    _md.update(sp_md)
    _md.update({'user_config': user_config})

    if len(jogging) == 3:
        _md["plan_name"] = "jog_areaDet"
        _md["jog_md"] = {
            "start": jogging[1],
            "stop": jogging[2],
            "motor": jogging[0].name
        }
        jogging_motor = jogging[0]
    else:
        jogging_motor = sample_y

    @bpp.reset_positions_decorator([jogging_motor.velocity])
    def inner_jog(gp, motor, start, stop):
        yield from bps.mv(motor, start)  # got to initial position
        yield from bps.mv(motor.velocity, abs(stop - start) / (exposure), timeout=1)
        yield from bps.abs_set(motor, stop, group=gp)  # set motor to move towards end

    @bpp.stage_decorator(dets)
    @bpp.run_decorator(md=_md)
    def trigger_and_wait() -> MsgGenerator:
        for det in dets:

            nonlocal jogging
            if len(jogging) == 3:
                print(f'Star to jog using {jogging[0].name}',
                      f'from {jogging[1]} mm to {jogging[2]} mm')
                gp = short_uid("rocker")
                yield from inner_jog(
                    gp,
                    motor=jogging[0],
                    start=jogging[1],
                    stop=jogging[2]
                )

            yield from bps.trigger(det, wait=True)
            yield from bps.create(name=stream_name)
            yield from bps.read(det)
            yield from bps.save()

    if not no_dark:
        yield from periodic_dark(trigger_and_wait())
        yield from bps.mv(fs_motor, 20)

    else:
        # yield from open_shutter_stub()
        yield from bps.mv(fs_motor, -20)
        yield from trigger_and_wait()
        # yield from close_shutter_stub()
        yield from bps.mv(fs_motor, 20)
