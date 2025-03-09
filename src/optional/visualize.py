"""
Module which is used for visualizing different data.

It is not an essential part of the whole project but helps to detect bugs.
"""

import sys
from typing import Any

from listener import fourie_transform

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

    graph: Any = None
    plt_initialized: bool = False
    sampling_rate: int

    def __init__(self, sampling_rate: int) -> None:
        self.sampling_rate = sampling_rate

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

    def process(self, data: bytes) -> None:
        """
        Processes update of `data`.

        Should be called every time new `data` is available.
        """

        if mp_disabled:
            return

        if self.graph is not None:
            self.graph.remove()

        # if plot window is closed
        if self.plt_initialized and len(plt.get_fignums()) == 0:
            sys.exit(0)

        fft = fourie_transform(data)
        self.graph = plt.plot(self.generate_x_values(
            len(fft),
            self.sampling_rate / 2),
            fft,
            color=(0, 0, 1)
        )[0]

        plt.show(block=False)
        plt.pause(0.001)
        self.plt_initialized = True
