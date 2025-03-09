from math import ceil
from threading import Thread
from time import sleep
from pyaudio import PyAudio, Stream, paInt16


class SoundListenerSync:
    '''
    Listens (and decodes) bytes that were transmitted using one of sound sender classes.
    '''

    audio: PyAudio
    input_stream: Stream

    sampling_rate: int
    frames_per_buffer: int
    is_listening: bool
    duration: float
    available_frames: list[list[bytes]]

    def __init__(self, sampling_rate: int = 44100, frames_per_buffer: int = 1024, duration: float = 0.25) -> None:
        self.audio = PyAudio()
        self.sampling_rate = sampling_rate
        self.frames_per_buffer = frames_per_buffer
        self.duration = duration
        self.input_stream = self.audio.open(
            format=paInt16,
            channels=1,
            rate=self.sampling_rate,
            frames_per_buffer=self.frames_per_buffer,
            input=True,
        )
        self.is_listening = False
        self.available_frames = []

    def listen(self) -> None:
        '''
        Starts listening.
        Puts available data to `self.available_frames` periodically.
        '''
        self.is_listening = True

    def pause_listening(self) -> None:
        self.is_listening = False

    def process(self) -> None:
        for _i in range(0, ceil(self.sampling_rate / self.frames_per_buffer * self.duration)):
            data: bytes = self.input_stream.read(self.frames_per_buffer)
            # print(data)
            # self.is_listening = False
            # FIXME:
            self.available_frames.append([data])

    def cleanup(self) -> None:
        self.input_stream.stop_stream()
        self.input_stream.close()
        self.audio.terminate()


class SoundListener:
    sync_listener: SoundListenerSync
    sound_thread: Thread
    is_disposing: bool

    def __init__(self, **kwargs: ...) -> None:
        self.sync_listener = SoundListenerSync(**kwargs)
        self.sound_thread = Thread(target=self._sound_loop)
        self.is_disposing = False

        self.sound_thread.start()

    def _cleanup(self) -> None:
        self.sync_listener.cleanup()

    def _sound_loop(self) -> None:
        while not self.is_disposing:
            if self.sync_listener.is_listening:
                self.sync_listener.process()

            sleep(0.001)

        self._cleanup()

    def listen(self) -> None:
        self.sync_listener.is_listening = True

    def dispose(self, **kwargs: ...) -> None:
        self.is_disposing = True
        self.sound_thread.join(**kwargs)

    def pop_available_frames(self) -> list[list[bytes]]:
        frames: list[list[bytes]] = self.sync_listener.available_frames
        self.sync_listener.available_frames = []
        return frames

