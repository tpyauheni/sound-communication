import time
from listener import SoundListener
from soundcom.audio import SoundBatch
from soundcom.audioconsts import *
from optional.visualize import Visualizer


class SoundSender:
    batch: SoundBatch
    listener: SoundListener
    visualizer: Visualizer

    def __init__(self) -> None:
        self.batch = SoundBatch()
        self.listener = SoundListener()
        self.visualizer = Visualizer()

    def initialize_communication(self) -> None:
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
        self.listener.listen()

        while True:
            frames: list[list[bytes]] = self.listener.pop_available_frames()

            if len(frames) > 0:
                frame: list[bytes] = frames[-1]
                # print(1)
                # FIXME [0] at the end:
                self.visualizer.process(frame[0])
                continue

        # self.visualizer.process(data)

    def dispose(self) -> None:
        self.batch.dispose()


def main() -> None:
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
