"""
Sound communication.
"""

import time
from typing import Any

import numpy as np
from numpy.typing import NDArray

from error_corrector import ErrorCorrector
from listener import SoundListener, SoundListenerSync, fourie_transform
from optional.visualize import Visualizer

from soundcom.audio import SoundBatch
from soundcom.audioconsts import FREQ_CONTROL, FREQ_TRANSMIT, FREQ_COUNTER
from soundcom.audioconsts import CH3_FREQ_STEP, CH3_TRANSFER_BITS
from soundcom.audioconsts import CH3_FREQ_START

# Treshold which is used to indicate whether bit is considered ON
# If set too low, it may assume environmental noise as a sent bit.
# If set too high, it may assume sent bit as environmental noise.
INITIAL_TRESHOLD: float = 1.5 * 10**6
TRESHOLD: float = 8.0 * 10**6

FIRST_BATCH_DELAY: float = 0.065

# Amount of captures of microphone input buffer per second.
# If set too high, there may not be enough data to perform an accurate FFT.
# If set too low, it may skip batches of bits sent from other peer.
INPUT_UPDATES_PER_SECOND: int = 30


class SoundSender:
    """
    Class which is used to play batches of sound (i.e. send them).
    """

    batch: SoundBatch
    listener: SoundListener
    visualizer: Visualizer
    skip_frames: bool
    prev_batch_time: float | None
    cumulative_input: bytes

    def __init__(
        self,
        duration: float = 0.5,
        skip_frames: bool = False,
    ) -> None:
        frames_per_buffer: int = SoundListenerSync.DEFAULT_SAMPLING_RATE // \
            INPUT_UPDATES_PER_SECOND

        self.batch = SoundBatch(duration=duration)
        self.listener = SoundListener(
            frames_per_buffer=frames_per_buffer,
            duration=duration,
        )
        self.visualizer = Visualizer(self.listener.sync_listener.sampling_rate)
        self.skip_frames = skip_frames
        self.prev_batch_time = None
        self.cumulative_input = bytes()

    def initialize_communication(self) -> None:
        """
        Performs initialization sequence. Generates cryptographic keys and
        exchanges them with another client.
        """
        raise NotImplementedError('TODO')

    def _split_by_bits(self, buffer: str, bits: int) -> list[str]:
        """
        Splits `buffer` by groups of equal size `bits`.
        """

        bit_groups: list[str] = []
        bit_start: int = 0

        while bit_start + 1 <= len(buffer):
            bit_groups.append(
                buffer[bit_start:bit_start + bits].zfill(bits))
            bit_start += bits

        return bit_groups

    def send_message(
        self,
        message: str,
        freq_start: float,
        freq_step: float,
        bits: int,
    ) -> None:
        """
        Converts `message` to bytes (in UTF-8 encoding), splits them by `bits`
        bits. And then sends resulting bytes using `SoundBatch`.

        @param freq_start: Frequency of the first data bit in the channel.
        @param freq_step: Frequency difference between any two nearest bits in
        the channel.
        """

        if bits > 8:
            raise ValueError('Bits should be at most 8')

        self.batch.enqueue([FREQ_COUNTER, FREQ_TRANSMIT])

        message_bytes: bytes = message.encode('UTF-8')
        counter: bool = False

        # for chunked_bytes in ErrorCorrector.break_into_frames(message_bytes):
        for chunked_bytes in [message_bytes]:
            # ec_bytes: bytes = ErrorCorrector(chunked_bytes).encode()
            ec_bytes = chunked_bytes
            print(ec_bytes)
            message_bits: str = ''

            for byte in ec_bytes:
                for bit in bin(byte)[2:].zfill(8):
                    message_bits += bit

            message_bit_groups: list[str] = self._split_by_bits(
                message_bits,
                bits,
            )

            for group in message_bit_groups:
                freq_buffer: list[float] = []

                if group.count('1') == 0:
                    freq_buffer.append(FREQ_TRANSMIT)
                else:
                    for i, bit in enumerate(group):
                        if bit == '1':
                            freq_buffer.append(freq_start + freq_step * i)

                if counter:
                    freq_buffer.append(FREQ_COUNTER)

                counter = not counter
                print(''.join([
                    '1' if freq in freq_buffer else '0' for freq in [
                        FREQ_COUNTER,
                        FREQ_TRANSMIT,
                        FREQ_CONTROL,
                        freq_start,
                        freq_start + freq_step,
                        freq_start + freq_step * 2,
                        freq_start + freq_step * 3,
                    ]
                ]))
                self.batch.enqueue(freq_buffer)

        freq_buffer: list[float] = []

        # Send `FREQ_CONTROL` to indicate end of the message
        freq_buffer.append(FREQ_CONTROL)

        if counter:
            freq_buffer.append(FREQ_COUNTER)

        print(freq_buffer)
        self.batch.enqueue(freq_buffer)
        self.batch.wait()
        print('Message sent')

    def _nearest(self, array: list[float], value: float) -> float:
        """
        Returns a value of an element in the `array` which is the nearest to
        `value`.
        """
        return min(array, key=lambda x: abs(x - value))

    def _freq_plusminus(self, base_freq: float, plusminus: float
                        ) -> tuple[float, float]:
        """
        Returns tuple with two elements: `base_freq` ± `plusminus`.
        """
        return (base_freq - plusminus, base_freq + plusminus)

    def reduce_noise(
            self,
            freq_step: float,
            frequencies: list[float],
            x_values: list[float],
            values: list[np.float64],
            fft: NDArray[Any],
    ) -> list[np.float64]:
        """
        Returns difference between every element of `values` and environmental
        noise.

        @param freq_step: Difference between two nearest data bit frequencies
        in the channel.
        @param frequencies: List of original frequencies to reduce noise from.
        @param x_values: List of real frequencies on FFT.
        @param values: List of FFT values nearest on `frequencies` list.
        @param fft: List of original FFT values on `x_values` as frequency
        list.
        """

        # Off frequencies are frequencies that are supposed to be always off,
        # e.g. not included in overall transmission process.
        off_frequencies: list[tuple[float, float]] = [
            self._freq_plusminus(freq, freq_step // 2) for freq in frequencies]

        nearest_off_freqs: list[tuple[int, int]] = []

        for freq_pair in off_frequencies:
            nearest_off_freqs.append((
                x_values.index(self._nearest(x_values, freq_pair[0])),
                x_values.index(self._nearest(x_values, freq_pair[1])),
            ))

        noise_values: list[tuple[np.float64, np.float64]] = [
            (fft[x[0]], fft[x[1]]) for x in nearest_off_freqs]
        avg_noise: list[np.float64] = [
            (x[0] + x[1]) / 2.0 for x in noise_values]

        assert len(values) == len(avg_noise)

        reduced_noise_values: list[np.float64] = [
            values[i] - avg_noise[i] for i in range(len(values))
        ]

        return reduced_noise_values

    def _update_listener(
        self,
        buffer: bytearray,
        set_bits: list[bool],
        final_bit_buffer: list[bool],
    ) -> list[bool]:
        """
        Updates listener.

        @param buffer: Byte buffer to which result will be appended to.
        @param final_bit_buffer: Temporary list of bits to which result will
            be appended on counter bit change.
        """

        final_bit_buffer.extend(set_bits)

        if len(final_bit_buffer) >= 8:
            buffer.append(
                int(
                    ''.join(
                        [
                            '01'[bit]
                            for bit in final_bit_buffer[:8]
                        ],
                    ),
                    2,
                ),
            )

            final_bit_buffer = final_bit_buffer[8:]

        return final_bit_buffer

    def _get_set_bits(
        self,
        fft: NDArray[Any],
        frequencies: list[float],
        treshold: float,
    ) -> list[bool]:
        x_values = self.visualizer.generate_x_values(
            len(fft),
            self.listener.sync_listener.sampling_rate / 2,
        )

        nearest_freqs: list[int] = []

        for freq in frequencies:
            nearest_freqs.append(x_values.index(self._nearest(
                x_values, freq)))

        values: list[np.float64] = [fft[x] for x in nearest_freqs]

        # FIXME: NOISE REDUCTION IS INSECURE!!!
        # UNDER RIGHT CIRCUMSTANCES ATTACKER CAN REWRITE ANY MESSAGE TO
        # WHATEVER HE WANTS!
        # Overwriting OFF bit to ON is as simple as sending a single sine frequency (works even without noise reduction)
        # Overwriting ON bit to OFF is as simple as sending a frequencies exactly in range of noise reduction; that will detect ON bit as noise and set it to OFF
        # values = self.reduce_noise(
        #     freq_step,
        #     frequencies,
        #     x_values,
        #     values,
        #     fft,
        # )

        set_bits: list[bool] = []

        for value in values:
            set_bits.append(bool(value >= treshold))

        return set_bits

    def listen_for_first_batch(
        self,
        fft: NDArray[Any],
        frequencies: list[float],
        frame: bytes,
    ) -> None:
        set_bits: list[bool] = self._get_set_bits(
            fft,
            frequencies,
            INITIAL_TRESHOLD,
        )
        ones: int = set_bits.count(True)

        if ones < 2 or ones == len(set_bits):
            return

        self.prev_batch_time = time.time() - FIRST_BATCH_DELAY
        print(f'First batch time (receiver): {self.prev_batch_time}')
        self.cumulative_input += frame

    def _update_receiver(
        self,
        buffer: bytearray,
        final_bit_buffer: list[bool],
        frequencies: list[float],
        freq_start: float,
        freq_step: float,
        bits: int,
        prev_counter: bool,
        frame: bytes,
    ) -> tuple[bool, bool, list[bool]]:
        """
        Updates receiver.

        # Returns
        Tuple with three values:
        - Value that will be specified as `prev_counter` on the next call.
        - Was there no bits set on FFT.
        - Modified `final_bit_buffer`.
        """

        assert(self.prev_batch_time is not None)

        time_elapsed: float = time.time() - self.prev_batch_time
        duration: float = self.listener.sync_listener.duration

        if time_elapsed < duration:
            self.cumulative_input += frame
            return (prev_counter, True, final_bit_buffer)

        print(f'{(time_elapsed - duration):.2f}')
        self.prev_batch_time += duration

        fft = fourie_transform(self.cumulative_input)
        self.cumulative_input = bytes()
        set_bits = self._get_set_bits(
            fft,
            frequencies,
            TRESHOLD,
        )

        self.visualizer.process(fft)
        self.visualizer.process_bits(
            set_bits,
            freq_start,
            freq_step,
            bits,
            TRESHOLD,
        )

        if set_bits.count(True) < 2:
            return (prev_counter, True, final_bit_buffer)

        counter_now: bool = set_bits[0]
        _empty_message: bool = set_bits[1]
        flush_buffer: bool = set_bits[2]

        if counter_now != prev_counter or True:
            final_bit_buffer = self._update_listener(
                buffer,
                set_bits,
                final_bit_buffer,
            )
            prev_counter = counter_now

        if buffer and flush_buffer and sum(set_bits) == 1 + counter_now:
            print_buffer: bytes = bytes(buffer)

            try:
                print_buffer = ErrorCorrector(print_buffer).decode()
            except ValueError as exc:
                print(exc)

            try:
                print(print_buffer.decode('UTF-8'))
            except UnicodeError:
                print(print_buffer.hex())

            buffer.clear()

        bit_buffer: list[bool] = []

        for bit in set_bits[3:]:
            bit_buffer.append(bit)

        no_message: bool = sum(set_bits) <= counter_now
        final_bit_buffer.extend(bit_buffer)
        print(''.join(['1' if bit else '0' for bit in set_bits]))
        return (prev_counter, no_message, final_bit_buffer)

    def receive_loop(
        self,
        freq_start: float,
        freq_step: float,
        bits: int,
    ) -> None:
        """
        Receives messages from other peer in an infinite loop.

        If required libraries are installed, also shows visualization of FFT.
        """
        self.listener.listen()
        frequencies: list[float] = [FREQ_COUNTER, FREQ_TRANSMIT, FREQ_CONTROL]

        for bit in range(bits):
            frequencies.append(freq_start + freq_step * bit)

        # Assuming sender already sent `False`, so it will accept `True` next.
        prev_counter: bool = False
        connected: bool = False

        buffer: bytearray = bytearray()
        final_bit_buffer: list[bool] = []

        silence_start: float | None = None

        while True:
            frames: list[bytes] = self.listener.pop_available_frames()

            while len(frames) > 0:
                frame: bytes

                if len(frames) > 10 and self.skip_frames:
                    frame = frames.pop()
                    frames.clear()
                    print('SKIPPING FRAMES TO SPEED UP')
                else:
                    frame = frames.pop(0)

                if self.prev_batch_time is None:
                    fft = fourie_transform(frame)

                    if len(frames) == 0:
                        self.visualizer.process(fft)
                        self.visualizer.process_bits(
                            self._get_set_bits(
                                fft,
                                frequencies,
                                INITIAL_TRESHOLD,
                            ),
                            freq_start,
                            freq_step,
                            bits,
                            INITIAL_TRESHOLD,
                        )

                    self.listen_for_first_batch(fft, frequencies, frame)
                    continue

                new_counter, no_message, new_bit_buffer = self._update_receiver(
                    buffer,
                    final_bit_buffer,
                    frequencies,
                    freq_start,
                    freq_step,
                    bits,
                    prev_counter,
                    frame,
                )

                final_bit_buffer = new_bit_buffer

                if not connected and prev_counter != new_counter:
                    connected = True

                prev_counter = new_counter

                if connected and no_message:
                    if silence_start is None:
                        silence_start = time.time()
                    elif time.time() - silence_start >= 5.0:
                        print('Disconnected')
                        connected = False
                        silence_start = None
                        prev_counter = False
                        buffer.clear()
                        final_bit_buffer.clear()
                else:
                    silence_start = None

    def dispose(self) -> None:
        """
        Cleans up used resources.

        The instance of that class should not be used after calling
        `dispose()`.
        """
        self.batch.dispose()


def main() -> None:
    """
    Function which is called if file is being launched directly by Python
    and not imported in any other project.
    """

    sender: SoundSender = SoundSender(duration=0.5)
    mode: str

    while True:
        mode = input(
            'Select mode [sender / receiver / batch]: ').lower()

        match mode:
            case 's' | 'sn' | 'snd' | 'send' | 'sender':
                mode = 'sender'
                break
            case 'r' | 're' | 'rec' | 'recv' | 'receiver':
                mode = 'receiver'
                break
            case 'b' | 'bt' | 'batch':
                mode = 'batch'
                break
            case _:
                print('Invalid mode')

    try:
        if mode == 'sender':
            while True:
                str_to_transfer: str = input('Enter string to transfer: ')
                sender.send_message(
                    str_to_transfer,
                    CH3_FREQ_START,
                    CH3_FREQ_STEP,
                    CH3_TRANSFER_BITS,
                )
        elif mode == 'receiver':
            sender.receive_loop(
                CH3_FREQ_START,
                CH3_FREQ_STEP,
                CH3_TRANSFER_BITS,
            )
        else:
            sender = SoundSender(duration=20.0)

            frequencies: list[float] = [
                FREQ_COUNTER,
                FREQ_TRANSMIT,
                FREQ_CONTROL,
                *[
                    CH3_FREQ_START + CH3_FREQ_STEP * i
                    for i in range(CH3_TRANSFER_BITS)
                ],
            ]

            while True:
                bitmask: str = input('Enter bitmask to play: ').zfill(6)

                if (
                    len(bitmask) != 6 or
                    bitmask.count('0') + bitmask.count('1') != 6
                ):
                    print('Invalid bitmask')
                    continue

                freq_buffer: list[float] = []

                for i, bit in enumerate(bitmask):
                    if bit == '0':
                        continue

                    freq_buffer.append(frequencies[i])

                print('Playing... ', end='', flush=True)

                sender.batch.enqueue(freq_buffer)

                try:
                    sender.batch.wait()
                except KeyboardInterrupt:
                    sender.batch.reset()

                print('OK')

        sender.dispose()
    except KeyboardInterrupt:
        sender.dispose()
    except SystemExit as exc:
        sender.dispose()
        raise exc


if __name__ == '__main__':
    main()
