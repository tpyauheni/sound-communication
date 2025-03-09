"""
Module which gets and processes input from the microphone.
"""

import struct

from math import ceil
from threading import Thread
from time import sleep
from typing import Any
from numpy.typing import NDArray
from pyaudio import PyAudio, Stream, paInt16

import numpy as np


class SoundListenerSync:
    """
    Listens (and decodes) bytes that were transmitted using one of sound
    sender classes.

    It does so in the current thread.
    """

    audio: PyAudio
    input_stream: Stream

    sampling_rate: int
    frames_per_buffer: int
    is_listening: bool
    duration: float
    available_frames: list[bytes]

    def __init__(self,
                 sampling_rate: int = 44100,
                 frames_per_buffer: int = 1024,
                 duration: float = 0.25) -> None:
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
        """
        Starts listening.
        Puts available data to `self.available_frames` periodically.
        """
        self.is_listening = True

    def pause_listening(self) -> None:
        """
        Pauses listening process.
        It can be resumed by calling `self.listen()`.
        """
        self.is_listening = False

    def process(self) -> None:
        """
        Reads batch of data from the microphone.
        Size of that batch is determined by `self.frames_per_buffer`.
        """
        for _i in range(0, ceil(
            self.sampling_rate /
            self.frames_per_buffer * self.duration
        )):
            data: bytes = self.input_stream.read(self.frames_per_buffer)
            self.available_frames.append(data)

    def cleanup(self) -> None:
        """
        Cleans up resources after using that listener.

        After calling `cleanup()`, the listener should not be used anymore.
        """
        self.input_stream.stop_stream()
        self.input_stream.close()
        self.audio.terminate()


class SoundListener:
    """
    Wrapper around `SoundListenerSync` in another thread.
    """

    sync_listener: SoundListenerSync
    sound_thread: Thread
    is_disposing: bool

    def __init__(self, **kwargs: Any) -> None:
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
        """
        Starts listening.
        Puts available data to `self.available_frames` periodically.
        """
        self.sync_listener.is_listening = True

    def dispose(self, **kwargs: Any) -> None:
        """
        Cleans up resources after using that listener.

        After calling `dispose()`, the listener should not be used anymore.
        """
        self.is_disposing = True
        self.sound_thread.join(**kwargs)

    def pop_available_frames(self) -> list[bytes]:
        """
        Returns all available frames at the current moment of time.
        It also clears a list with all available frames.
        """
        frames: list[bytes] = self.sync_listener.available_frames
        self.sync_listener.available_frames = []
        return frames


def fourie_transform(data: bytes) -> NDArray[Any]:
    """
    Performs fast Fourie transform on given microphone input `data`.
    """
    data2 = np.array(
        struct.unpack(f'{len(data) // 2}h', data),
        dtype=np.int16
    )
    split_data = np.split(np.abs(np.fft.fft(data2)), 2)
    fft = np.add(split_data[0], split_data[1][::-1])
    return fft
