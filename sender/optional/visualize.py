# import pyfftw
import numpy as np
import sys
import struct

mp_disabled: bool = False

# try:
# from typing import Optional
# import matplotlib as mp
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
# except ImportError:
#     mp_disabled = True

class Visualizer:
    MAX_FREQUENCY: float = 20_000.0
    X_VALUES_MEMO: dict[int, list[float]] = {}

    graph: Line2D | None = None
    plt_initialized: bool = False

    def __init__(self) -> None:
        if mp_disabled:
            return

        # plt.ylim(0.0, 1.0)

    def generate_x_values(self, length: int, max_freq: float) -> list[float]:
        if length in Visualizer.X_VALUES_MEMO:
            return Visualizer.X_VALUES_MEMO[length]

        result: list[float] = [0.0]

        for i in range(1, length):
            result.append(max_freq / (length - 1) * i)

        Visualizer.X_VALUES_MEMO[length] = result
        return result

    def process(self, data: bytes) -> None:
        if self.graph is not None:
            self.graph.remove()

        # input_data: list[int] = struct.unpack(f'{len(data)//2}h', data)
        # input_data: list[float] = [struct.unpack('@H', data[i * 2:i * 2 + 2])[0] / 65536.0 * 1.0 for i in range(len(data) // 2)]
        # input_np = np.array(input_data, dtype=np.int16)
        # freq_vector = np.linspace(0, 44_100 // 2, len(input_np) // 2)
        # fft = np.fft.fft(freq_vector)
        # freq = np.abs(fft) / len(fft)
        # fftw_input = pyfftw.empty_aligned(len(input_data), dtype='float64')
        # fftw_output = pyfftw.empty_aligned(len(input_data) // 2 + 1, dtype='complex128')
        # fftw_input[...] = input_data
        # fft = pyfftw.FFTW(fftw_input, fftw_output, threads=7)
        # fft(fftw_input)
        # input_data = np.array()
        # print(input_data)
        # fft = pyfftw.builders.fft(input_data)
        # pyfftw.FFTW()
        # output_data = fft()
        # output_data = output_data[:len(output_data) // 2 - 1]
        # w = np.fft.fft(input_np)
        # freqs = np.abs((np.fft.fftfreq(len(w))*44_100))
        # w = np.abs(w)
        # indices = np.argsort(w)[int(len(w)*.99):]
        # indices = indices[len(indices)%10:]
        # w = w[indices]
        # freqs = freqs[indices]
        # w = w[np.argsort(freqs)]
        # freqs = np.sort(freqs)
        # w = np.reshape(w, (-1, 10)).sum(axis=1)
        # freqs = np.average(np.reshape(freqs, (-1, 10)), axis=1)
        # w /= np.sum(w)
        # freqdict = dict(zip(freqs, w))
        # print(freqdict)
        # output_data = freq
        # x_values = self.generate_x_values(len(output_data))
        # output_data = input_data

        # if plot window was closed
        # if self.plt_initialized and len(plt.get_fignums()) == 0:
            # sys.exit(0)

        # print(freqs, np.array([np.min(w)*2]*len(freqs)))
        # self.graph = plt.plot(freqs, np.array([np.min(w)*2]*len(freqs)), color=(0,0,1), zorder=-1)[0]
        # result = []
        # insidePeak = False

        # t = np.min(w)*3

        # row = []

        # for height, freq in zip(w, freqs):

        #     if freq < 100:
        #         continue

        #     if height > t:
        #         insidePeak = True
        #     else:
        #         if insidePeak:
        #             result.append(sorted(row)[-1])
        #             row = []
        #         insidePeak = False

        #     if insidePeak:
        #         row.append((height, freq)) 

        # plt.scatter(np.array([x[1] for x in result]), np.array([x[0] for x in result]))

        # mul = 1/np.sum(np.array([x[0] for x in result]))

        # resarr = []

        # for x in result:
        #     resarr.append({"Freq":x[1], "Volume":mul*x[0]})

        # if plot window was closed
        if self.plt_initialized and len(plt.get_fignums()) == 0:
            sys.exit(0)

        data2 = np.array(struct.unpack(f'{len(data) // 2}h', data))
        left, right = np.split(np.abs(np.fft.fft(data2)), 2)
        fft = np.add(left, right[::-1])
        self.graph = plt.plot(self.generate_x_values(len(fft), 44100.0 / 2), fft, color=(0, 0, 1))[0]

        plt.show(block=False)
        # TODO: Connect `close` event of plot to `sys.exit(0)`
        plt.draw()
        plt.pause(0.001)
        self.plt_initialized = True
