"""
Sound communication.
"""

import time
from listener import SoundListener, fourie_transform
from optional.visualize import Visualizer

from soundcom.audio import SoundBatch
from soundcom.audioconsts import CH1_FREQ_START, CH1_FREQ_STEP
from soundcom.audioconsts import CH1_TRANSFER_BITS, FREQ_TRANSMIT


class SoundSender:
    """
    Class which is used to play batches of sound (i.e. send them).
    """

    batch: SoundBatch
    listener: SoundListener
    visualizer: Visualizer

    def __init__(self) -> None:
        self.batch = SoundBatch()
        self.listener = SoundListener()
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

                if print_list:
                    print(print_list)

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

        while bit_start <= len(message_bits):
            message_bit_groups.append(
                message_bits[bit_start:bit_start + bits].zfill(bits))
            bit_start += bits

        print(message_bit_groups)

        for group in message_bit_groups:
            self.batch.reset()

            if group.count('1') == 0:
                self.batch.add(FREQ_TRANSMIT)
            else:
                for i, bit in enumerate(group):
                    if bit == '1':
                        self.batch.add(freq_start + freq_step * i)

            self.batch.play()
            self.batch.wait()

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

    sender_mode: bool = input('Select mode [Sender / receiver]: '
                              ).lower() not in [
                                  'r',
                                  'recv',
                                  're',
                                  'rec',
                                  'receiver',
                              ]

    try:
        if sender_mode:
            str_to_transfer: str = input('Enter string to transfer: ')
            sender.send_message(
                str_to_transfer,
                CH1_FREQ_START,
                CH1_FREQ_STEP * 2.0,
                CH1_TRANSFER_BITS // 2,
            )
        else:
            # TODO:
            # sender.receive_loop(
            #     CH1_FREQ_START,
            #     CH1_FREQ_STEP * 2.0,
            #     CH1_TRANSFER_BITS // 2,
            # )
            pass

        # sender.listen_for_sounds()
        # sender.initialize_communication()
    except KeyboardInterrupt:
        sender.dispose()
    except SystemExit as exc:
        sender.dispose()
        raise exc


if __name__ == '__main__':
    main()
