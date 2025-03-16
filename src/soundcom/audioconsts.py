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


from typing import Any, Callable, Generator


class Freq:
    CHUNK_LENGTH: int = 4
    CHUNKS_COUNT: int = 6

    # It is a constant which is used to show minimum step, less than which
    # frequencies after FFT become illegible.
    STEP_HZ: float = 46.875
    CHANNEL_STEP: float = STEP_HZ * 2  # = 93.75 Hz

    CHANNELS: list[float] = [
        1_875.0,
        15_000.0,
    ]

    _base_frequency: float = 0.0

    def __init__(self, channel_id: int) -> None:
        try:
            self._base_frequency = self.CHANNELS[channel_id]
        except IndexError:
            raise ValueError(f'Expected `channel_id` to be a valid channel index.')

    def data(self, chunk_index: int, value: list[bool]) -> float:
        if chunk_index < 0 or chunk_index >= self.CHUNKS_COUNT:
            raise ValueError(f'Parameter `chunk_index` must be in interval [0; {self.CHUNKS_COUNT})')

        if not isinstance(value, list) or len(value) != self.CHUNK_LENGTH:
            raise ValueError(f'Parameter `value` must be a list with length {self.CHUNK_LENGTH}')

        variant_offset: int = int(''.join(['1' if x else '0' for x in value]), 2)
        return self._base_frequency + 2 ** self.CHUNK_LENGTH * self.STEP_HZ * chunk_index + self.STEP_HZ * variant_offset

    def data_list(self, data: list[list[bool]]) -> list[float]:
        if not isinstance(data, list) or len(data) != self.CHUNKS_COUNT:
            raise ValueError(f'Parameter `data` must be a list with length {self.CHUNKS_COUNT}')

        result: list[float] = []

        for i, bit_group in enumerate(data):
            if not isinstance(bit_group, list) or len(bit_group) != self.CHUNK_LENGTH:
                raise ValueError(f'Every element of parameter `data` must be a list with length {self.CHUNKS_COUNT}')

            result.append(self.data(i, bit_group))

        return result

    def decompose_data_list(self, data: list[Any], checker_func: Callable[[Any], bool]) -> list[list[bool]]:
        if not isinstance(data, list) or len(data) != self.CHUNKS_COUNT * self.CHUNK_LENGTH:
            raise ValueError(f'Parameter `data` must be a list with length {self.CHUNKS_COUNT * self.CHUNK_LENGTH}')

        result: list[list[bool]] = []

        for i in range(self.CHUNKS_COUNT):
            chunk: list[bool] = []

            for j in range(self.CHUNK_LENGTH):
                chunk.append(checker_func(data[i * self.CHUNK_LENGTH + j]))

            result.append(chunk)

        return result

    def channel_data_size(self) -> float:
        """
        Returns size (in Hz) of all the data bits in the current channel.
        """
        return self.STEP_HZ * 2 ** self.CHUNK_LENGTH * self.CHUNKS_COUNT

    def channel_size(self) -> float:
        return self.channel_data_size() + self.STEP_HZ

    def channel_range(self) -> tuple[float, float]:
        return (self._base_frequency, self._base_frequency + self.channel_size())

    def msg_bit(self) -> float:
        # We are given frequency of last possible data bits combination in the last chunk + `STEP_HZ`
        # so we just return it.
        return self.channel_data_size()

    def all(self) -> Generator[float]:
        for chunk in range(self.CHUNKS_COUNT):
            for part in range(self.CHUNK_LENGTH):
                yield self._base_frequency + (chunk * self.CHUNK_LENGTH + part) * self.STEP_HZ

        yield self.msg_bit()

