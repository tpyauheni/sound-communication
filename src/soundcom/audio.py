"""
Module used for various operations with audio.
"""

from threading import Thread
from array import array
from time import sleep

import math
from typing import Any

from pyaudio import PyAudio, paFloat32, Stream


class SoundBatchSync:
    """
    Sound batch which is playing given sounds synchronically (in the current
    thread).

    For asynchronous (non-blocking) playing of sounds look at `SoundBatch`.
    """

    audio: PyAudio
    output_stream: Stream

    volume: float
    sampling_rate: int
    is_playing: bool
    play_queued: bool
    duration: float
    sounds: list[float]

    def __init__(self, volume: float = 1.0, sampling_rate: int = 44100,
                 duration: float = 0.25) -> None:
        if volume < 0.0 or volume > 1.0:
            raise ValueError(f'Expected `volume` to be in range [0.0; 1.0], \
got {volume:.2f}')

        if sampling_rate <= 0:
            raise ValueError('Expected `sampling_rate` to be positive')

        if duration <= 0.0:
            raise ValueError('Expected `duration` to be positive')

        self.audio = PyAudio()
        self.sampling_rate = sampling_rate
        self.output_stream = self.audio.open(
            format=paFloat32,
            channels=1,
            rate=self.sampling_rate,
            output=True,
        )
        self.volume = volume
        self.is_playing = False
        self.play_queued = False
        self.duration = duration
        self.sounds = []

    def add(self, frequency: float) -> None:
        """
        Appends `frequency` to audio batch.
        """
        self.sounds.append(frequency)

    def play(self) -> None:
        """
        Starts playing frequencies that are currently in batch.

        If batch is already being played, queues it again.
        """
        if self.is_playing:
            self.play_queued = True
        else:
            self.is_playing = True

    def wait(self, timeout: float = -1.0, precision: float = 0.01) -> bool:
        """
        Sleeps every `precision` interval until either the batch will stop
        playing or `timeout` will expire.

        If `timeout` is <= 0.0 then it will never expire.
        """
        total_time: float = 0.0

        while self.is_playing:
            sleep(precision)
            total_time += precision

            if timeout > 0.0 and total_time >= timeout:
                return False

        return True

    def reset(self) -> None:
        """
        Stops playing and clears all frequencies in the batch, if play is
        queued, cancels it.
        """
        self.is_playing = False
        self.play_queued = False
        self.sounds.clear()

    def process(self) -> None:
        """
        Plays all frequencies in the batch for specific duration.
        """
        samples_count: int = int(self.sampling_rate * self.duration)
        samples: list[float] = [0.0 for _i in range(samples_count)]

        for sample_i in range(0, samples_count):
            for frequency in self.sounds:
                samples[sample_i] += math.sin(
                    math.tau * sample_i * frequency / self.sampling_rate
                ) * self.volume / len(self.sounds)

        # samples: list[float] = []

        # for i in range(samples_count):
            # samples.append(math.tau * i)

        samples_arr: array[float] = array('f', samples)
        sampled_bytes: bytes = samples_arr.tobytes()

        self.output_stream.write(sampled_bytes)
        self.is_playing = self.play_queued
        self.play_queued = False

    def cleanup(self) -> None:
        """
        Cleans up resources after using batch.

        After calling `cleanup()`, the batch should not be used.
        """
        self.output_stream.stop_stream()
        self.output_stream.close()
        self.audio.terminate()


class SoundBatch:
    """
    Sound batch which is playing given sounds asynchronically (in another
    thread).
    """

    sync_batch: SoundBatchSync
    sound_thread: Thread
    is_disposing: bool

    def __init__(self, **kwargs: Any) -> None:
        self.sync_batch = SoundBatchSync(**kwargs)
        self.sound_thread = Thread(target=self._sound_loop)
        self.is_disposing = False

        self.sound_thread.start()

    def _cleanup(self) -> None:
        self.sync_batch.cleanup()

    def _sound_loop(self) -> None:
        while not self.is_disposing:
            if self.sync_batch.is_playing:
                self.sync_batch.process()

            sleep(0.001)

        self._cleanup()

    def add(self, frequency: float) -> None:
        """
        Appends `frequency` to audio batch.
        """
        self.sync_batch.add(frequency)

    def play(self) -> None:
        """
        Starts playing frequencies that are currently in batch.

        If batch is already being played, queues it again.
        """
        self.sync_batch.play()

    def wait(self, timeout: float = -1.0, precision: float = 0.01) -> bool:
        """
        Sleeps every `precision` interval until either the batch will stop
        playing or `timeout` will expire.

        If `timeout` is <= 0.0 then it will never expire.
        """
        return self.sync_batch.wait(timeout, precision)

    def reset(self) -> None:
        """
        Stops playing and clears all frequencies in the batch, if play is
        queued, cancels it.
        """
        self.sync_batch.reset()

    def dispose(self, **kwargs: Any) -> None:
        """
        Cleans up resources after using batch.

        After calling `dispose()`, the batch should not be used.
        """
        self.is_disposing = True
        self.sound_thread.join(**kwargs)
