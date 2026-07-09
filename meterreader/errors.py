"""Exception hierarchy for the meter reader."""


class MeterReaderError(Exception):
    """Base class for all errors raised by this package."""


class RadioError(MeterReaderError):
    """The CC1101 transceiver could not be initialised or accessed.

    The receiver loop reacts to this by re-initialising the radio.
    """


class FrameDecodeError(MeterReaderError):
    """A received frame could not be decoded (noise, RF error, wrong key, ...).

    The receiver loop reacts to this by discarding the frame and waiting for
    the next one.
    """
