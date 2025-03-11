"""
Sound communication.
"""

import time
from typing import Any

import numpy as np
from numpy.typing import NDArray

from listener import SoundListener, SoundListenerSync, fourie_transform
from optional.visualize import Visualizer

from soundcom.audio import SoundBatch
from soundcom.audioconsts import *

TRESHOLD: float = 5.0 * 10**6


class SoundSender:
    """
    Class which is used to play batches of sound (i.e. send them).
    """

    batch: SoundBatch
    listener: SoundListener
    visualizer: Visualizer

    def __init__(self, duration: float = 0.5) -> None:
        self.batch = SoundBatch(duration=duration)
        self.listener = SoundListener(
            frames_per_buffer=SoundListenerSync.DEFAULT_SAMPLING_RATE // (
                4 + 1 + 4),
        )
        self.visualizer = Visualizer(self.listener.sync_listener.sampling_rate)

    def initialize_communication(self) -> None:
        """
        Performs initialization sequence. Generates cryptographic keys and
        exchanges them with another client.
        """

        while True:
            self.batch.add(500)
            self.batch.add(1000)
            self.batch.add(1500)
            self.batch.add(2000)
            self.batch.play()
            self.batch.wait()

            self.batch.reset()
            self.batch.add(500)
            self.batch.add(1500)
            self.batch.play()
            self.batch.wait()

            self.batch.reset()
            self.batch.add(1500)
            self.batch.add(2000)
            self.batch.play()
            time.sleep(10.0)

            self.batch.reset()

    def listen_for_sounds(self) -> None:
        """
        Listens for sounds from other client.
        """
        self.listener.listen()

        while True:
            frames: list[bytes] = self.listener.pop_available_frames()

            if len(frames) > 0:
                frame: bytes = frames[-1]
                fft = fourie_transform(frame)
                self.visualizer.process(fft)

                x_values = self.visualizer.generate_x_values(len(fft), 20_000)
                print_list: list[tuple[int, float, float]] = []

                for i, x in enumerate(fft):
                    # if frequency is less than 300
                    if x_values[i] < 300:
                        continue

                    if x >= 10**6:
                        print_list.append((i, x_values[i], x))

                # if print_list:
                #     print(print_list)

                continue

    def send_message(self, message: str, freq_start: float, freq_step: float,
                     bits: int) -> None:
        if bits > 8:
            raise ValueError('Bits should be at most 8')

        message_bytes: bytes = message.encode('UTF-8')
        message_bits: str = ''

        for byte in message_bytes:
            for bit in bin(byte)[2:].zfill(8):
                message_bits += bit

        message_bit_groups: list[str] = []
        bit_start: int = 0

        while bit_start + 1 <= len(message_bits):
            message_bit_groups.append(
                message_bits[bit_start:bit_start + bits].zfill(bits))
            bit_start += bits

        counter: bool = True

        for group in message_bit_groups:
            self.batch.reset()

            if group.count('1') == 0:
                self.batch.add(FREQ_TRANSMIT)
            else:
                for i, bit in enumerate(group):
                    if bit == '1':
                        self.batch.add(freq_start + freq_step * i)

            if counter:
                self.batch.add(FREQ_COUNTER)

            print('Sending', group, counter)

            counter = not counter

            self.batch.play()
            self.batch.wait()

        # Send zero byte, indicating end of the string
        self.batch.add(FREQ_TRANSMIT)

        if counter:
            self.batch.add(FREQ_COUNTER)

        self.batch.play()
        self.batch.wait()
        print('Message sent')

    def _nearest(self, array: list[float], value: float) -> float:
        return min(array, key=lambda x: abs(x - value))

    def _freq_plusminus(self, base_freq: float, plusminus: float
                        ) -> tuple[float, float]:
        return (base_freq - plusminus, base_freq + plusminus)

    def reduce_noise(
            self,
            freq_step: float,
            frequencies: list[float],
            x_values: list[float],
            values: list[np.float64],
            fft: NDArray[Any],
    ) -> list[np.float64]:
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

    def receive_loop(self, freq_start: float, freq_step: float, bits: int
                     ) -> None:
        self.listener.listen()
        frequencies: list[float] = [FREQ_COUNTER, FREQ_TRANSMIT]

        for bit in range(bits):
            frequencies.append(freq_start + freq_step * bit)

        # Assuming sender already sent `False`, so it will accept `True` next.
        prev_counter: bool = False

        # for bit in range(bits):
        #     off_frequencies.append(freq_start + freq_step * bit + freq_step // 2)

        buffer: bytearray = bytearray()
        final_bit_buffer: list[bool] = []
        bit_buffer_add_variants: list[list[bool]] = []
        warn_something_wrong: str | None = None

        silence_start: float | None = None

        while True:
            frames: list[bytes] = self.listener.pop_available_frames()

            while len(frames) > 0:
                # start: float = time.time()
                frame: bytes

                if len(frames) > 10:
                    frame = frames.pop()
                    frames.clear()
                else:
                    frame = frames.pop(0)

                fft = fourie_transform(frame)
                # TODO: Show only needed frequenices in the visualizer
                self.visualizer.process(fft)

                x_values = self.visualizer.generate_x_values(len(fft), 20_000)

                nearest_freqs: list[int] = []

                for freq in frequencies:
                    nearest_freqs.append(x_values.index(self._nearest(
                        x_values, freq)))

                values: list[np.float64] = [fft[x] for x in nearest_freqs]

                # reduced_noise_values: list[np.float64] = self.reduce_noise(
                #     freq_step, frequencies, x_values, values, fft)

                # print(no_noise_values)

                set_bits: list[bool] = []

                # for i, value in enumerate(reduced_noise_values):
                for i, value in enumerate(values):
                    set_bits.append(bool(value >= TRESHOLD))
                    # if value >= 10**6:
                    #     print(x_values[nearest_freqs[i]], f'{value:.2f}')

                # for i, bit in enumerate(set_bits):
                    # print(
                    #     f'{int(x_values[nearest_freqs[i]])}: {bit}', end=', ')

                # elapsed_time: float = time.time() - start
                # print(f'{elapsed_time:.4f}ms')

                self.visualizer.process_bits(set_bits, freq_start, freq_step,
                                             bits, TRESHOLD)

                if sum(set_bits) == 0:
                    if silence_start is None:
                        silence_start = time.time()
                        continue

                    if silence_start - time.time() > 5.0:
                        prev_counter = False
                        print('Counter was reset')

                    continue

                # print(''.join([str(1 if x else 0) for x in set_bits]))

                counter_now: bool = set_bits[0]

                if counter_now != prev_counter:
                    prev_counter = counter_now
                    dont_change: bool = False

                    if len(bit_buffer_add_variants) == 0:
                        dont_change = True

                    ones: list[int] = [0 for _i in range(bits)]

                    for variant in bit_buffer_add_variants:
                        for i, bit in enumerate(variant):
                            if bit:
                                ones[i] += 1

                    if not dont_change:
                        average_variant: list[bool] = []

                        for i, one_values in enumerate(ones):
                            one_value: float = one_values / len(
                                bit_buffer_add_variants)

                            if one_value > 0.5:
                                average_variant.append(True)
                            elif one_value < 0.5:
                                average_variant.append(False)
                            else:
                                print(f'UNSURE ABOUT BIT {i + 1};',
                                      'ASSUMING `FALSE`')
                                average_variant.append(False)

                        # print(bit_buffer_add_variants, average_variant)
                        final_bit_buffer.extend(average_variant)

                        # median_variant: list[bool] = bit_buffer_add_variants[
                        #     len(bit_buffer_add_variants) // 2]
                        # print(''.join([str(1 if x else 0)
                        #                for x in median_variant]))

                        if sum(average_variant) != 0:
                            dont_change = True

                            if warn_something_wrong is not None:
                                print('WARNING:', warn_something_wrong)

                        warn_something_wrong = None

                        # final_bit_buffer.extend(median_variant)

                        if len(final_bit_buffer) >= 8:
                            buffer.append(int(''.join(
                                ['01'[bit] for bit in final_bit_buffer[:8]]),
                                2))
                            # TODO: UTF-8
                            print(
                                chr(buffer[-1]),
                                buffer[-1],
                                bin(buffer[-1])[2:].zfill(8),
                            )
                            final_bit_buffer = final_bit_buffer[8:]

                        bit_buffer_add_variants.clear()

                if set_bits[1] and sum(set_bits[2:]) > 0:
                    warn_something_wrong = 'Received FREQ_TRANSMIT (used only \
to indicate empty message) is used with non-empty message'
                    continue

                bit_buffer: list[bool] = []

                for bit in set_bits[2:]:
                    bit_buffer.append(bit)

                bit_buffer_add_variants.append(bit_buffer)

                # print({x_values[nearest_freqs[i]]: set_bits[i]
                    #    for i in range(len(set_bits))})
                # print(values, avg_noise)

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

    sender: SoundSender = SoundSender()
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
                    CH3_FREQ_STEP * 2,
                    CH3_TRANSFER_BITS // 2,
                )
        elif mode == 'receiver':
            sender.receive_loop(
                CH3_FREQ_START,
                CH3_FREQ_STEP * 2,
                CH3_TRANSFER_BITS // 2,
            )
        else:
            sender = SoundSender(duration=20.0)

            frequencies: list[float] = [
                FREQ_COUNTER,
                FREQ_TRANSMIT,
                *[
                    CH3_FREQ_START + CH3_FREQ_STEP * 2 * i
                    for i in range(CH3_TRANSFER_BITS // 2)
                ],
            ]

            while True:
                bitmask: str = input('Enter bitmask to play: ').zfill(6)

                if len(bitmask) != 6 or bitmask.count('0') + bitmask.count('1') != 6:
                    print('Invalid bitmask')
                    continue

                sender.batch.reset()

                for i, bit in enumerate(bitmask):
                    if bit == '0':
                        continue

                    sender.batch.add(frequencies[i])

                print('Playing... ', end='', flush=True)

                sender.batch.play()

                try:
                    sender.batch.wait()
                except KeyboardInterrupt:
                    sender.batch.reset()

                print('OK')

        # sender.listen_for_sounds()
        # sender.initialize_communication()
        sender.dispose()
    except KeyboardInterrupt:
        sender.dispose()
    except SystemExit as exc:
        sender.dispose()
        raise exc


if __name__ == '__main__':
    main()
