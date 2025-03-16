"""
Module which is used for visualizing different data.

It is not an essential part of the whole project but helps to detect bugs.
"""

import sys
from typing import Any

from numpy.typing import NDArray

from soundcom.audioconsts import Freq

mp_disabled: bool = False

try:
    import matplotlib.pyplot as plt
except ImportError:
    mp_disabled = True


class Visualizer:
    """
    Class for general visualizations using `matplotlib`.
    """

    X_VALUES_MEMO: dict[int, list[float]] = {}

    main_graph: Any = None
    freq_marks: list[Any] = []

    plt_initialized: bool = False
    sampling_rate: int

    def __init__(self, sampling_rate: int) -> None:
        self.sampling_rate = sampling_rate

    def _cut_frequencies(
        self,
        x_values: list[float],
        values: NDArray[Any],
        cutoff_frequency: float,
    ) -> tuple[list[float], NDArray[Any]]:
        min_index: int = 0

        for i, freq in enumerate(x_values):
            if freq > cutoff_frequency:
                break

            min_index = i + 1

        return (x_values[min_index:], values[min_index:])

    def generate_x_values(self, length: int, max_freq: float) -> list[float]:
        """
        Generates array of frequencies in range [0; `max_freq`] with total
        length `length`.
        """

        if length in Visualizer.X_VALUES_MEMO:
            return Visualizer.X_VALUES_MEMO[length]

        result: list[float] = [0.0]

        for i in range(1, length):
            result.append(max_freq / (length - 1) * i)

        Visualizer.X_VALUES_MEMO[length] = result
        return result

    def process(self, data: NDArray[Any]) -> None:
        """
        Processes update of `data` which is a result from FFT function.

        Should be called every time new `data` is available.
        """

        if mp_disabled:
            return

        if self.main_graph is not None:
            self.main_graph.remove()

        # if plot window is closed
        if self.plt_initialized and len(plt.get_fignums()) == 0:
            sys.exit(0)

        x_values = self.generate_x_values(
            len(data),
            self.sampling_rate / 2
        )

        self.main_graph = plt.plot(
            *self._cut_frequencies(
                x_values,
                data,
                300,
            ),
            color=(0, 0, 1)
        )[0]

        plt.show(block=False)
        plt.pause(0.001)
        self.plt_initialized = True

    def process_bits(
        self,
        bits_set: list[bool],
        freq: Freq,
        treshold: float,
        width: float = 20.0,
    ) -> None:
        if mp_disabled:
            return

        for mark in self.freq_marks:
            mark.remove()

        self.freq_marks.clear()

        frequencies: list[float] = list(freq.all())

        for i, bit in enumerate(bits_set):
            frequency = frequencies[i]
            self.freq_marks.append(plt.plot(
                [frequency - width / 2.0, frequency + width / 2.0],
                [treshold, treshold],
                color='#ff8000' if bit else '#0080ff',
            )[0])

