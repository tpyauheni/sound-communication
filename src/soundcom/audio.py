"""
Module used for various operations with audio.
"""

from queue import Queue
import queue
from threading import Thread
from array import array
from time import sleep

import math
import time
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
    duration: float

    first_batch_played: bool = False

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
        self.duration = duration

    def play(self, sample: bytes) -> None:
        """
        Starts playing frequencies that are currently in batch.

        If batch is already being played, queues it again.
        """
        if not self.first_batch_played:
            print(f'First batch time (sender): {time.time()}')

        self.first_batch_played = True
        self.output_stream.write(sample)

    def cleanup(self) -> None:
        """
        Cleans up resources after using batch.

        After calling `cleanup()`, the batch should not be used.
        """
        self.output_stream.stop_stream()
        self.output_stream.close()
        self.audio.terminate()

    def sample_frequencies(self, frequencies: list[float]) -> bytes:
        samples_count: int = int(self.sampling_rate * self.duration)
        samples: list[float] = [0.0 for _i in range(samples_count)]

        for sample_i in range(0, samples_count):
            for frequency in frequencies:
                samples[sample_i] += math.sin(
                    math.tau * sample_i * frequency / self.sampling_rate
                ) * self.volume / len(frequencies)

        samples_arr: array[float] = array('f', samples)
        sampled_bytes: bytes = samples_arr.tobytes()
        return sampled_bytes

    def reset(self) -> None:
        pass


class SoundBatch:
    """
    Sound batch which is playing given sounds asynchronically (in another
    thread).
    """

    sync_batch: SoundBatchSync
    sound_thread: Thread
    sampler_thread: Thread
    is_disposing: bool
    frequencues_queue: Queue[list[float]]
    samples_queue: Queue[bytes]

    def __init__(self, **kwargs: Any) -> None:
        self.sync_batch = SoundBatchSync(**kwargs)
        self.sound_thread = Thread(target=self._sound_loop)
        self.sampler_thread = Thread(target=self._sample_loop)
        self.is_disposing = False
        self.frequencues_queue = Queue(maxsize=5)
        self.samples_queue = Queue(maxsize=64)

        self.sound_thread.start()
        self.sampler_thread.start()

    def _cleanup(self) -> None:
        self.sync_batch.cleanup()

    def _sound_loop(self) -> None:
        while not self.is_disposing:
            self.sync_batch.play(self.samples_queue.get())

    def _sample_loop(self) -> None:
        while not self.is_disposing:
            sample: bytes = self.sync_batch.sample_frequencies(
                self.frequencues_queue.get(),
            )
            self.samples_queue.put(sample)

    def enqueue(self, frequencies: list[float]) -> None:
        self.frequencues_queue.put(frequencies)

    def wait(self, timeout: float = -1.0, precision: float = 0.01) -> bool:
        """
        Sleeps every `precision` interval until either the batch will stop
        playing or `timeout` will expire.

        If `timeout` is <= 0.0 then it will never expire.
        """

        start_time: float = time.time()

        while (
            self.samples_queue.qsize() > 0 or
            self.frequencues_queue.qsize() > 0
        ):
            sleep(precision)

            if timeout <= 0.0:
                continue

            if time.time() - start_time >= timeout:
                return False

        return True

    def reset(self) -> None:
        """
        Stops playing and clears all frequencies in the batch, if play is
        queued, cancels it.
        """

        try:
            while True:
                self.frequencues_queue.get(block=False)
        except queue.Empty:
            pass

        try:
            while True:
                self.samples_queue.get(block=False)
        except queue.Empty:
            pass

        self.sync_batch.reset()

    def dispose(self, **kwargs: Any) -> None:
        """
        Cleans up resources after using batch.

        After calling `dispose()`, the batch should not be used.
        """
        self.is_disposing = True
        self.sound_thread.join(**kwargs)
        self.sampler_thread.join(**kwargs)
        self.sync_batch.cleanup()
