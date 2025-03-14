"""
Module that defines some constants for sound communication protocol.

The protocol itself:

'>' means peer 1 sends a message to peer 2 (or broadcasts it to everyone).
'<' means peer 2 sends a message to peer 1.

`CH<channel>(binary data)` means `(CH<channel>_FREQ_START +
    (CH<channel>_FREQ_STEP * binary_data[0])) | ...`

> FREQ_INIT
< CH1(10100000)
> CH1(00100010)
> CH1(channel), i.e.
    CH1(00000000) for x = CH1,
    CH1(00000010) for x = CH2,
    CH1(00001000) for x = CH3,
    CH1(00001010) for x = CH4
< CHx(10000010) to begin session or CHx(00101000) if unsupported, not complete
    or invalid data.

TODO: ECDH key exchange

But for now:
> CHx(8 bits of data)
...
< CHx(8 bits of data)
...
> FREQ_CONTROL (is only used to disconnect for now)
    Also may be '< FREQ_CONTROL'
"""

# It is a constant which is used to show minimum step, less than which
# frequencies after FFT become illegible.
__STEP_HZ = 43.15068493150685

# Control constants that are not part of overall data communication.
FREQ_INIT: float = 430 * __STEP_HZ  # ~= 18555 Hz
# `FREQ_CONTROL` is used in following cases:
# - if all other bits are off (excluding counter which may or may not be set)
# then it is used to indicate end of the buffer;
# - other usages are planned.
FREQ_CONTROL: float = 410 * __STEP_HZ  # = 17692 Hz
# `FREQ_TRANSMIT` is used to indicate that all zeroes are being transmitted.
FREQ_TRANSMIT: float = 390 * __STEP_HZ  # ~= 16829 Hz
# `FREQ_COUNTER` bit is set if it was unset in the previous frequency group;
# unset otherwise.
FREQ_COUNTER: float = 370 * __STEP_HZ  # ~= 15966 Hz

# Channel 1:
CH1_FREQ_START: float = 100 * __STEP_HZ  # ~= 4315 Hz
CH1_FREQ_STEP: float = 10 * __STEP_HZ
CH1_TRANSFER_BITS: int = 8  # ends on 170 * __STEP_HZ ~= 7336 Hz

# Channel 2:
# it is 190 not 180 on purpose
CH2_FREQ_START: float = 190 * __STEP_HZ  # ~= 8199 Hz
CH2_FREQ_STEP: float = 10 * __STEP_HZ
CH2_TRANSFER_BITS: int = 8  # ends on 260 * __STEP_HZ ~= 11219 Hz

# Channel 3:
CH3_FREQ_START: float = 280 * __STEP_HZ  # ~= 12082 Hz
CH3_FREQ_STEP: float = 10 * __STEP_HZ
CH3_TRANSFER_BITS: int = 8  # ends on 350 * __STEP_HZ ~= 15103 Hz

# Channel 4 (overlaps with control bits, so don't use!):
CH4_FREQ_START: float = 370 * __STEP_HZ  # ~= 15966 Hz
CH4_FREQ_STEP: float = 10 * __STEP_HZ
CH4_TRANSFER_BITS: int = 4  # ends on 400 * __STEP_HZ ~= 17692 Hz

# Channel 5:
CH5_FREQ_START: float = 460 * __STEP_HZ  # ~= 19849 Hz
CH5_FREQ_STEP: float = 10 * __STEP_HZ
CH5_TRANSFER_BITS: int = 4  # ends on 490 * __STEP_HZ ~= 21575 Hz
