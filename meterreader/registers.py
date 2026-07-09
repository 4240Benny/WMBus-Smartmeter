"""CC1101 register addresses and related constants.

Section and table references are to the Texas Instruments CC1101 data sheet
(SWRS061I).
"""

import enum


class Strobe(enum.IntEnum):
    """Command strobes (table 42)."""

    SRES = 0x30  # reset chip
    SFSTXON = 0x31
    SXOFF = 0x32
    SCAL = 0x33
    SRX = 0x34  # enable RX
    STX = 0x35
    SIDLE = 0x36  # exit RX/TX
    SWOR = 0x38
    SPWD = 0x39
    SFRX = 0x3A  # flush RX FIFO
    SFTX = 0x3B  # flush TX FIFO
    SWORRST = 0x3C
    SNOP = 0x3D


class ConfigReg(enum.IntEnum):
    """Configuration registers (table 43)."""

    IOCFG2 = 0x00  # GDO2 output pin configuration
    IOCFG1 = 0x01  # GDO1 output pin configuration
    IOCFG0 = 0x02  # GDO0 output pin configuration
    FIFOTHR = 0x03  # RX FIFO and TX FIFO thresholds
    SYNC1 = 0x04  # sync word, high byte
    SYNC0 = 0x05  # sync word, low byte
    PKTLEN = 0x06  # packet length
    PKTCTRL1 = 0x07  # packet automation control
    PKTCTRL0 = 0x08  # packet automation control
    ADDR = 0x09  # device address
    CHANNR = 0x0A  # channel number
    FSCTRL1 = 0x0B  # frequency synthesizer control
    FSCTRL0 = 0x0C  # frequency synthesizer control
    FREQ2 = 0x0D  # frequency control word, high byte
    FREQ1 = 0x0E  # frequency control word, middle byte
    FREQ0 = 0x0F  # frequency control word, low byte
    MDMCFG4 = 0x10  # modem configuration
    MDMCFG3 = 0x11  # modem configuration
    MDMCFG2 = 0x12  # modem configuration
    MDMCFG1 = 0x13  # modem configuration
    MDMCFG0 = 0x14  # modem configuration
    DEVIATN = 0x15  # modem deviation setting
    MCSM2 = 0x16  # main radio control state machine configuration
    MCSM1 = 0x17  # main radio control state machine configuration
    MCSM0 = 0x18  # main radio control state machine configuration
    FOCCFG = 0x19  # frequency offset compensation configuration
    BSCFG = 0x1A  # bit synchronization configuration
    AGCCTRL2 = 0x1B  # AGC control
    AGCCTRL1 = 0x1C  # AGC control
    AGCCTRL0 = 0x1D  # AGC control
    WOREVT1 = 0x1E  # high byte event 0 timeout
    WOREVT0 = 0x1F  # low byte event 0 timeout
    WORCTRL = 0x20  # wake on radio control
    FREND1 = 0x21  # front end RX configuration
    FREND0 = 0x22  # front end TX configuration
    FSCAL3 = 0x23  # frequency synthesizer calibration
    FSCAL2 = 0x24  # frequency synthesizer calibration
    FSCAL1 = 0x25  # frequency synthesizer calibration
    FSCAL0 = 0x26  # frequency synthesizer calibration
    RCCTRL1 = 0x27  # RC oscillator configuration
    RCCTRL0 = 0x28  # RC oscillator configuration
    FSTEST = 0x29  # frequency synthesizer calibration control
    PTEST = 0x2A  # production test
    AGCTEST = 0x2B  # AGC test
    TEST2 = 0x2C  # various test settings
    TEST1 = 0x2D  # various test settings
    TEST0 = 0x2E  # various test settings


class StatusReg(enum.IntEnum):
    """Status registers (table 44); read with the burst bit set."""

    PARTNUM = 0x30
    VERSION = 0x31
    FREQEST = 0x32
    LQI = 0x33
    RSSI = 0x34
    MARCSTATE = 0x35
    WORTIME1 = 0x36
    WORTIME0 = 0x37
    PKTSTATUS = 0x38
    VCO_VC_DAC = 0x39
    TXBYTES = 0x3A
    RXBYTES = 0x3B
    RCCTRL1_STATUS = 0x3C
    RCCTRL0_STATUS = 0x3D


FIFO_ADDRESS = 0x3F  # section 10.5: TX FIFO on write, RX FIFO on read


class MarcState(enum.IntEnum):
    """Main radio control state machine states (MARCSTATE register)."""

    SLEEP = 0x00
    IDLE = 0x01
    XOFF = 0x02
    VCOON_MC = 0x03
    REGON_MC = 0x04
    MANCAL = 0x05
    VCOON = 0x06
    REGON = 0x07
    STARTCAL = 0x08
    BWBOOST = 0x09
    FS_LOCK = 0x0A
    IFADCON = 0x0B
    ENDCAL = 0x0C
    RX = 0x0D
    RX_END = 0x0E
    RX_RST = 0x0F
    TXRX_SWITCH = 0x10
    RXFIFO_OVERFLOW = 0x11
    FSTXON = 0x12
    TX = 0x13
    TX_END = 0x14
    RXTX_SWITCH = 0x15
    TXFIFO_UNDERFLOW = 0x16


class PacketLengthMode(enum.IntEnum):
    """PKTCTRL0.LENGTH_CONFIG"""

    FIXED = 0b00
    VARIABLE = 0b01
    INFINITE = 0b10
