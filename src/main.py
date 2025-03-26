"""
Sound communication.
"""

import time
import sys
from typing import Any

import numpy as np
from numpy.typing import NDArray

from error_corrector import ErrorCorrector
from listener import SoundListener, SoundListenerSync, fourie_transform
from log import LOGGER
from optional.visualize import Visualizer

from soundcom.audio import SoundBatch
from soundcom.audioconsts import Freq

import alternative as alt

# Treshold which is used to indicate whether bit is considered ON
# If set too low, it may assume environmental noise as a sent bit.
# If set too high, it may assume sent bit as environmental noise.
INITIAL_TRESHOLD: float = 1.5 * 10**6
TRESHOLD: float = 8.0 * 10**6

FIRST_BATCH_DELAY: float = 0.065

# Amount of captures of microphone input buffer per second.
# If set too high, there may not be enough data to perform an accurate FFT.
# If set too low, it may skip batches of bits sent from other peer.
INPUT_UPDATES_PER_SECOND: float = SoundListenerSync.DEFAULT_SAMPLING_RATE / 1024.0


class SoundSender:
    """
    Class which is used to play batches of sound (i.e. send them).
    """

    batch: SoundBatch
    listener: SoundListener
    visualizer: Visualizer
    freq: Freq
    skip_frames: bool
    prev_batch_time: float | None
    cumulative_input: bytes

    def __init__(
        self,
        duration: float = 0.5,
        skip_frames: bool = False,
        channel_id: int = -1,
    ) -> None:
        frames_per_buffer: int = int(SoundListenerSync.DEFAULT_SAMPLING_RATE /
            INPUT_UPDATES_PER_SECOND)

        self.batch = SoundBatch(duration=duration)
        self.listener = SoundListener(
            frames_per_buffer=frames_per_buffer,
            duration=duration,
        )
        self.visualizer = Visualizer(self.listener.sync_listener.sampling_rate)
        self.freq = Freq(channel_id)
        self.skip_frames = skip_frames
        self.prev_batch_time = None
        self.cumulative_input = bytes()

    def initialize_communication(self) -> None:
        """
        Performs initialization sequence. Generates cryptographic keys and
        exchanges them with another client.
        """
        raise NotImplementedError('TODO')

    def _split_by_bits(self, buffer: list[bool]) -> list[list[bool]]:
        """
        Splits `buffer` by groups of equal size `bits`.
        """

        bit_groups: list[list[bool]] = []
        bit_start: int = 0

        while bit_start + 1 <= len(buffer):
            bit_groups.append(
                [
                    True if x else False
                    for x in buffer[bit_start:bit_start + self.freq.CHUNK_LENGTH]
                ]
            )
            bit_start += self.freq.CHUNK_LENGTH

        return bit_groups

    def send_message(
        self,
        message: str,
    ) -> None:
        """
        Converts `message` to bytes (in UTF-8 encoding), splits them by `bits`
        bits. And then sends resulting bytes using `SoundBatch`.
        """

        self.batch.enqueue([self.freq.msg_bit()])

        message_bytes: bytes = message.encode('UTF-8')

        # for chunked_bytes in ErrorCorrector.break_into_frames(message_bytes):
        for chunked_bytes in [message_bytes]:
            # ec_bytes: bytes = ErrorCorrector(chunked_bytes).encode()
            ec_bytes = chunked_bytes
            LOGGER.verbose('Sending chunk:', ec_bytes)
            message_bits: list[bool] = []

            for byte in ec_bytes:
                for bit in bin(byte)[2:].zfill(8):
                    message_bits.append(bit == '1')

            message_bit_groups: list[list[bool]] = self._split_by_bits(
                message_bits,
            )

            while len(message_bit_groups) >= self.freq.CHUNKS_COUNT:
                freq_buffer: list[float] = self.freq.data_list(message_bit_groups[:self.freq.CHUNKS_COUNT])
                message_bit_groups = message_bit_groups[self.freq.CHUNKS_COUNT:]
                LOGGER.info('Frequencies:', freq_buffer)
                self.batch.enqueue(freq_buffer)

            if len(message_bit_groups) > 0:
                for _i in range(self.freq.CHUNKS_COUNT - len(message_bit_groups)):
                    message_bit_groups.append([False for _j in range(self.freq.CHUNK_LENGTH)])

                freq_buffer: list[float] = self.freq.data_list(message_bit_groups)
                LOGGER.info('Frequencies (last):', freq_buffer)
                self.batch.enqueue(freq_buffer)

        self.batch.enqueue([self.freq.msg_bit()])
        self.batch.wait()
        LOGGER.info('Message sent')

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

        # `decompose_data_list` takes only data values so we exclude message bit
        data_values: list[float] = values[:-1]

        for chunk in self.freq.decompose_data_list(data_values, lambda x: x >= treshold):
            for bit in chunk:
                set_bits.append(bit)

        return set_bits

    def listen_for_first_batch(
        self,
        fft: NDArray[Any],
        frequencies: list[float],
        frame: bytes,
        treshold: float = INITIAL_TRESHOLD,
    ) -> None:
        set_bits: list[bool] = self._get_set_bits(
            fft,
            frequencies,
            treshold,
        )

        message_bit = set_bits[-1]

        if not message_bit:
            return

        self.prev_batch_time = time.time() - FIRST_BATCH_DELAY
        LOGGER.verbose(f'First batch time (receiver)')
        self.cumulative_input += frame

    def _update_receiver(
        self,
        buffer: bytearray,
        final_bit_buffer: list[bool],
        frequencies: list[float],
        frame: bytes,
    ) -> list[bool]:
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
            return final_bit_buffer

        self.prev_batch_time += duration

        fft = fourie_transform(self.cumulative_input)
        self.cumulative_input = bytes()
        set_bits = self._get_set_bits(
            fft,
            frequencies,
            TRESHOLD,
        )

        message_bit: bool = set_bits[-1]

        if message_bit:
            LOGGER.verbose('End of message detected')

        self.visualizer.process(fft)
        self.visualizer.process_bits(
            set_bits,
            self.freq,
            TRESHOLD,
        )

        final_bit_buffer = self._update_listener(
            buffer,
            set_bits,
            final_bit_buffer,
        )

        bit_buffer: list[bool] = []

        for bit in set_bits[3:]:
            bit_buffer.append(bit)

        final_bit_buffer.extend(bit_buffer)
        LOGGER.verbose(''.join(['1' if bit else '0' for bit in set_bits]))
        return final_bit_buffer

    def receive_loop(
        self,
    ) -> None:
        """
        Receives messages from other peer in an infinite loop.

        If required libraries are installed, also shows visualization of FFT.
        """

        self.listener.listen()
        frequencies: list[float] = [*self.freq.all()]

        buffer: bytearray = bytearray()
        final_bit_buffer: list[bool] = []

        while True:
            frames: list[bytes] = self.listener.pop_available_frames()

            while len(frames) > 0:
                frame: bytes

                if len(frames) > 10 and self.skip_frames:
                    frame = frames.pop()
                    frames.clear()
                    LOGGER.warning('Skipping frames to speed up')
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
                            self.freq,
                            INITIAL_TRESHOLD,
                        )

                    self.listen_for_first_batch(fft, frequencies, frame)
                    continue

                new_bit_buffer = self._update_receiver(
                    buffer,
                    final_bit_buffer,
                    frequencies,
                    frame,
                )
                final_bit_buffer = new_bit_buffer

    def visualize_loop(
        self,
    ) -> None:
        """
        Visualizes FFT from sound input in an infinite loop if required libraries are installed.
        """

        self.listener.listen()

        while True:
            frames: list[bytes] = self.listener.pop_available_frames()

            if len(frames) == 0:
                continue

            frame = frames.pop()
            frames.clear()
            fft = fourie_transform(frame)

            if len(frames) == 0:
                self.visualizer.process(fft)
                time.sleep(0.01)

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

    # alt.ReliableTransceiver(alt.AlternativeStream(True, True)).session_start()
    # return
    # gui.show()

    mode: str
    fsk_method: str

    while True:
        print(
            'Select mode [sender / receiver / monitor]:', flush=True)
        mode: str = input().lower()

        match mode:
            case 's' | 'sn' | 'snd' | 'send' | 'sender':
                mode = 'sender'
                fsk_method = 'sender.original'
                break
            case 'r' | 're' | 'rec' | 'recv' | 'receiver':
                mode = 'receiver'
                fsk_method = 'receiver.original'
                break
            case 'm' | 'mn' | 'mon' | 'mntr' | 'monitor':
                mode = 'monitor'
                fsk_method = 'monitor.original'
                break
            case _:
                print('Invalid mode')

    try:
        if mode == 'sender':
            if not mode.endswith('originаl'):
                alt.sender()
                return

            sender: SoundSender = SoundSender(duration=0.5)

            while True:
                print('Enter string to transfer:', flush=True)
                str_to_transfer: str = input()
                sender.send_message(
                    str_to_transfer,
                )
        elif mode == 'receiver':
            if not mode.endswith('originаl'):
                alt.receiver()
                return

            sender: SoundSender = SoundSender(duration=0.5)
            sender.receive_loop()
        elif mode == 'monitor':
            sender: SoundSender = SoundSender()
            sender.visualize_loop()
        else:
            print('not implemented yet')
            return
            sender = SoundSender(duration=20.0)

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
        # sender.dispose()
        pass
    except SystemExit as exc:
        # sender.dispose()
        raise exc

    sys.exit(0)


if __name__ == '__main__':
    main()
