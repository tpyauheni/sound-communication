"""
Sound communication.
"""

import time
from listener import SoundListener
from soundcom.audio import SoundBatch
# from soundcom.audioconsts import FREQ_INIT
from optional.visualize import Visualizer


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
        self.visualizer = Visualizer()

    def initialize_communication(self) -> None:
        """
        Performs initialization sequence. Generates cryptographic keys and
        exchanges them with another client.
        """

        while True:
            # self.batch.add(FREQ_INIT)
            # self.batch.add(10_000)

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
                self.visualizer.process(frame)
                continue

        # self.visualizer.process(data)

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

    # str_to_transfer: str = input('Enter string to transfer: ')
    sender: SoundSender = SoundSender()

    try:
        sender.listen_for_sounds()
        sender.initialize_communication()
        # sender.transfer_retry(str_to_transfer)
    except KeyboardInterrupt:
        sender.dispose()
    except SystemExit as exc:
        sender.dispose()
        raise exc


if __name__ == '__main__':
    main()
