"""Take a scan with an aera detector for PDF or XRD."""

from collections.abc import Sequence

import bluesky.preprocessors as bpp
from bluesky.protocols import Readable
from ophyd import EpicsMotor
from xpdacq.beamtimeSetup import start_xpdacq
from xpdacq.xpdacq import (
    _inject_analysis_stage,
    _inject_calibration_md,
    _inject_qualified_dark_frame_uid,
)

from xpd_tools.actions import trigger_area_detector


def scan_with_dark(
    bt: start_xpdacq,
    dets: Sequence[Readable],
    fs_motor: EpicsMotor,
    exposure: float = 0.1,
    sample_id: int = 0,
    sample_info: dict | None = None,
    md: dict | None = None,
    stream_name: str = 'primary',
    no_dark: bool = False,
    jogging: list | None = None,
    frame_acq_time: float = 0.1,
    user_config: dict | None = None,
    ):
    """Take a scan with an aera detector for PDF or XRD.

    Args:
        dets (list):
            list of detector ophyd object, e.g., [piatus1] or [pe1c]

        exposure (float, optional):
            total exposure (measurement) time in seconds.
            Defaults to 0.1.

        sample_ID (int, optional):
            sample index returned in bt.list().
            Defaults to 0.

        sample_info (dict, optional):
            when sample_ID is not given or found, pass sample_name and
            composition_string as dict here.
            e.g.,
            sample_info = {
                'sample_name':'CeO2_quartz',
                'composition_string':'CeO2'
                }
            Defaults to None.

        md (dict, optional):
            additional metadata.
            e.g., md = {'note':'dummy test'}
            Defaults to None.

        stream_name (str, optional):
            stream name in the event document, 'primary' is recommended.
            Defaults to 'primary'.

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
        str: uid

    Yields
    ------
        msg: Msg
    """
    try:
        # Inject sample metadata from Excel spreadsheet
        sample_meta: dict = bt.samples.sel(sample_id)

    except (KeyError, IndexError):
        # Inject sample metadata manually from sample_info
        sample_meta: dict = sample_info

    print(f'\n***** sample_name = {sample_meta["sample_name"]} *****')

    # Check composition string
    try:
        print('\n***** composition_string = ',
             f'{sample_meta["composition_string"]} *****\n')
    except KeyError:
        sample_meta["composition_string"] = 'Ni1.0'
        print('\n***** composition_string = ',
             f'{sample_meta["composition_string"]} (dummy) *****\n')

    if isinstance(md, dict):
        md.update(sample_meta)
    else:
        md = sample_meta

    # while passing plan as a generator, no need to add "yield from"
    grand_plan = trigger_area_detector(
        fs_motor=fs_motor,
        dets=dets,
        exposure=exposure,
        stream_name=stream_name,
        md=md,
        no_dark=no_dark,
        jogging=jogging,
        frame_acq_time=frame_acq_time,
        user_config=user_config)

    if not no_dark:
        grand_plan = bpp.msg_mutator(grand_plan, _inject_qualified_dark_frame_uid)

    grand_plan = bpp.msg_mutator(grand_plan, _inject_calibration_md)
    grand_plan = bpp.msg_mutator(grand_plan, _inject_analysis_stage)
    return (yield from grand_plan)
