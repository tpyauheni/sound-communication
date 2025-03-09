from threading import Thread
from array import array
from time import sleep

import math

from pyaudio import PyAudio, paFloat32, Stream

# audio = PyAudio()

# volume = 0.5  # range [0.0, 1.0]
# fs = 44100  # sampling rate, Hz, must be integer
# duration = 5.0  # in seconds, may be float
# f = 440.0  # sine frequency, Hz, may be float

# generate samples, note conversion to float32 array
# num_samples = int(fs * duration)
# samples = [volume * math.sin(2 * math.pi * k * f / fs) for k in range(0, num_samples)]

# per @yahweh comment explicitly convert to bytes sequence
# output_bytes = array.array('f', samples).tobytes()

# for paFloat32 sample values must be in range [-1.0, 1.0]
# stream = p.open(format=pyaudio.paFloat32,
#                 channels=1,
#                 rate=fs,
#                 output=True)

# play. May repeat with different volume values (if done interactively)
# start_time = time.time()
# stream.write(output_bytes)
# print("Played sound for {:.2f} seconds".format(time.time() - start_time))

# stream.stop_stream()
# stream.close()

# p.terminate()


class SoundBatchSync:
    """
    Sound batch which is playing given sounds synchronically (in the current thread).

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

    def __init__(self, volume: float = 1.0, sampling_rate: int = 44100, duration: float = 0.25) -> None:
        if volume < 0.0 or volume > 1.0:
            raise ValueError(f'Expected `volume` to be in range [0.0; 1.0], got {volume:.2f}')

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
        self.sounds.append(frequency)

    def play(self) -> None:
        print('PLAY', self.is_playing, self.play_queued)
        if self.is_playing:
            self.play_queued = True
        else:
            self.is_playing = True
        print('after', self.is_playing, self.play_queued)

    def wait(self, timeout: float = -1.0, precision: float = 0.01) -> bool:
        total_time = 0.0

        while self.is_playing:
            sleep(precision)
            total_time += precision

            if timeout > 0.0 and total_time >= timeout:
                return False

        return True

    def reset(self) -> None:
        self.is_playing = False
        self.play_queued = False
        self.sounds.clear()
        print('RESET')

    def process(self) -> None:
        samples_count: int = int(self.sampling_rate * self.duration)
        samples: list[float] = [0.0 for _i in range(samples_count)]

        for sample_i in range(0, samples_count):
            for frequency in self.sounds:
                samples[sample_i] += math.sin(math.tau * sample_i * frequency / self.sampling_rate) * self.volume

        samples_arr: array[float] = array('f', samples)
        sampled_bytes: bytes = samples_arr.tobytes()

        self.output_stream.write(sampled_bytes)
        print('WAS: ', self.is_playing, self.play_queued)
        self.is_playing = self.play_queued
        self.play_queued = False
        print('BECAME: ', self.is_playing, self.play_queued)

    def cleanup(self) -> None:
        self.output_stream.stop_stream()
        self.output_stream.close()
        self.audio.terminate()


class SoundBatch:
    sync_batch: SoundBatchSync
    sound_thread: Thread
    is_disposing: bool

    def __init__(self, **kwargs: ...) -> None:
        self.sync_batch = SoundBatchSync(**kwargs)
        self.sound_thread = Thread(target=self._sound_loop)
        self.is_disposing = False

        self.sound_thread.start()

    def _cleanup(self) -> None:
        self.sync_batch.cleanup()

    def _sound_loop(self) -> None:
        while not self.is_disposing:
            if self.sync_batch.is_playing:
                print('PROC')
                self.sync_batch.process()

            sleep(0.001)

        self._cleanup()

    def add(self, frequency: float) -> None:
        self.sync_batch.add(frequency)

    def play(self) -> None:
        self.sync_batch.play()

    def wait(self, timeout: float = -1.0, precision: float = 0.01) -> bool:
        return self.sync_batch.wait(timeout, precision)

    def reset(self) -> None:
        self.sync_batch.reset()

    def dispose(self, **kwargs: ...) -> None:
        self.is_disposing = True
        self.sound_thread.join(**kwargs)
