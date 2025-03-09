"""
Module which is used for visualizing different data.

It is not an essential part of the whole project but helps to detect bugs.
"""

import sys
import struct
from typing import Any

import numpy as np

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

    def __init__(self) -> None:
        pass

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

        data2 = np.array(struct.unpack(f'{len(data) // 2}h', data))
        split_data = np.split(np.abs(np.fft.fft(data2)), 2)
        fft = np.add(split_data[0], split_data[1][::-1])
        self.graph = plt.plot(self.generate_x_values(len(fft), 44100.0 / 2),
                              fft, color=(0, 0, 1))[0]

        plt.show(block=False)
        plt.pause(0.001)
        self.plt_initialized = True
