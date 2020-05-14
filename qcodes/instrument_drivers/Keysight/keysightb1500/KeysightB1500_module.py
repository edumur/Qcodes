import re
from typing import Optional, Tuple, TYPE_CHECKING, Dict, Union, cast
from collections import namedtuple

from qcodes import InstrumentChannel
from .message_builder import MessageBuilder
from . import constants
from .constants import ModuleKind, SlotNr
if TYPE_CHECKING:
    from .KeysightB1500_base import KeysightB1500


_FMTResponse = namedtuple('FMTResponse', 'value status channel type')


def parse_fmt_1_0_response(raw_data_val: str) -> _FMTResponse:
    """
    Parse the response from SPA for `FMT 1,0` format  into a named tuple
    with names, value (value of the data), status (Normal or with compliance
    error such as C, T, V), channel (channel number of the output data such
    as CH1,CH2), type (current 'I' or voltage 'V').

    Args:
        raw_data_val: Unparsed (raw) data for the instrument.
    """

    values_separator = ','
    data_val = []
    data_status = []
    data_channel = []
    data_datatype = []

    for str_value in raw_data_val.split(values_separator):
        status = str_value[0]
        channel_id = constants.ChannelName[str_value[1]].value

        datatype = str_value[2]
        value = float(str_value[3:])

        data_val.append(value)
        data_status.append(status)
        data_channel.append(channel_id)
        data_datatype.append(datatype)

    data = _FMTResponse(data_val, data_status, data_channel, data_datatype)
    return data


def parse_module_query_response(response: str) -> Dict[SlotNr, str]:
    """
    Extract installed module information from the given string and return the
    information as a dictionary.

    Args:
        response: Response str to `UNT? 0` query.

    Returns:
        Dictionary from slot numbers to model name strings.
    """
    pattern = r";?(?P<model>\w+),(?P<revision>\d+)"

    moduleinfo = re.findall(pattern, response)

    return {
        SlotNr(slot_nr): model
        for slot_nr, (model, rev) in enumerate(moduleinfo, start=1)
        if model != "0"
    }


# pattern to match dcv experiment
_pattern_lrn = re.compile(
    r"(?P<status_dc>\w{1,3})(?P<chnr_dc>\w),(?P<voltage_dc>\d{1,3}.\d{1,4});"
    r"(?P<status_ac>\w{1,3})(?P<chnr_ac>\w),(?P<voltage_ac>\d{1,3}.\d{1,4});"
    r"(?P<status_fc>\w{1,2})(?P<chnr_fc>\w),(?P<frequency>\d{1,6}.\d{1,4})"
)


def parse_dcv_measurement_response(response: str) -> Dict[str, Union[str,
                                                                     float]]:
    """
    Extract status, channel number, value  and accompanying metadata from
    the string and return them as a dictionary.

    Args:
        response: Response str to lrn_query For the MFCMU.
    """

    match = re.match(_pattern_lrn, response)
    if match is None:
        raise ValueError(f"{response!r} didn't match {_pattern_lrn!r} pattern")

    dd = match.groupdict()
    d = cast(Dict[str, Union[str, float]], dd)
    return d


# Pattern to match the spot measurement response against
_pattern = re.compile(
    r"((?P<status>\w)(?P<chnr>\w)(?P<dtype>\w))?"
    r"(?P<value>[+-]\d{1,3}\.\d{3,6}E[+-]\d{2})"
)


def parse_spot_measurement_response(response: str) -> dict:
    """
    Extract measured value and accompanying metadata from the string
    and return them as a dictionary.

    Args:
        response: Response str to spot measurement query.

    Returns:
        Dictionary with measured value and associated metadata (e.g.
        timestamp, channel number, etc.)
    """
    match = re.match(_pattern, response)
    if match is None:
        raise ValueError(f"{response!r} didn't match {_pattern!r} pattern")

    dd = match.groupdict()
    d = cast(Dict[str, Union[str, float]], dd)
    d["value"] = float(d["value"])

    return d


_DCORRResponse = namedtuple('_DCORRResponse', 'mode primary secondary')


def parse_dcorr_query_response(response: str) -> _DCORRResponse:
    """
    Parse string response of ``DCORR?`` `command into a named tuple of
    :class:`constants.DCORR.Mode` and primary and secondary reference or
    calibration values.
    """
    mode, primary, secondary = response.split(',')
    return _DCORRResponse(mode=constants.DCORR.Mode(int(mode)),
                          primary=float(primary),
                          secondary=float(secondary))


_dcorr_labels_units_map = {
    constants.DCORR.Mode.Cp_G: dict(
        primary=dict(label='Cp', unit='F'),
        secondary=dict(label='G', unit='S')
    ),
    constants.DCORR.Mode.Ls_Rs: dict(
        primary=dict(label='Ls', unit='H'),
        secondary=dict(label='Rs', unit='Ω'))
}


def format_dcorr_response(r: _DCORRResponse) -> str:
    """
    Format a given response tuple ``_DCORRResponse`` from
    ``DCORR?`` command as a human-readable string.
    """
    labels_units = _dcorr_labels_units_map[r.mode]
    primary = labels_units['primary']
    secondary = labels_units['secondary']

    result_str = \
        f"Mode: {r.mode.name}, " \
        f"Primary {primary['label']}: {r.primary} {primary['unit']}, " \
        f"Secondary {secondary['label']}: {r.secondary} {secondary['unit']}"

    return result_str


# TODO notes:
# - [ ] Instead of generating a Qcodes InstrumentChannel for each **module**,
#   it might make more sense to generate one for each **channel**


class B1500Module(InstrumentChannel):
    """Base class for all modules of B1500 Parameter Analyzer

    When subclassing,

      - set ``MODULE_KIND`` attribute to the correct module kind
        :class:`~.constants.ModuleKind` that the module is.
      - populate ``channels`` attribute according to the number of
        channels that the module has.

    Args:
        parent: Mainframe B1500 instance that this module belongs to
        name: Name of the instrument instance to create. If `None`
            (Default), then the name is autogenerated from the instrument
            class.
        slot_nr: Slot number of this module (not channel number)
    """
    MODULE_KIND: ModuleKind

    def __init__(self, parent: 'KeysightB1500', name: Optional[str], slot_nr,
                 **kwargs):
        # self.channels will be populated in the concrete module subclasses
        # because channel count is module specific
        self.channels: Tuple
        self.slot_nr = SlotNr(slot_nr)

        if name is None:
            number = len(parent.by_kind[self.MODULE_KIND]) + 1
            name = self.MODULE_KIND.lower() + str(number)

        super().__init__(parent=parent, name=name, **kwargs)

    # Response parsing functions as static methods for user convenience
    parse_spot_measurement_response = parse_spot_measurement_response
    parse_module_query_response = parse_module_query_response

    def enable_outputs(self):
        """
        Enables all outputs of this module by closing the output relays of its
        channels.
        """
        # TODO This always enables all outputs of a module, which is maybe not
        # desirable. (Also check the TODO item at the top about
        # InstrumentChannel per Channel instead of per Module.
        msg = MessageBuilder().cn(self.channels).message
        self.write(msg)

    def disable_outputs(self):
        """
        Disables all outputs of this module by opening the output relays of its
        channels.
        """
        # TODO See enable_output TODO item
        msg = MessageBuilder().cl(self.channels).message
        self.write(msg)

    def is_enabled(self) -> bool:
        """
        Check if channels of this module are enabled.

        Returns:
            `True` if *all* channels of this module are enabled. `False`,
            otherwise.
        """
        # TODO If a module has multiple channels, and only one is enabled, then
        # this will return false, which is probably not desirable.
        # Also check the TODO item at the top about InstrumentChannel per
        # Channel instead of per Module.
        msg = (MessageBuilder()
               .lrn_query(constants.LRN.Type.OUTPUT_SWITCH)
               .message
               )
        response = self.ask(msg)
        activated_channels = re.sub(r"[^,\d]", "", response).split(",")

        is_enabled = set(self.channels).issubset(
            int(x) for x in activated_channels if x is not ''
        )
        return is_enabled
