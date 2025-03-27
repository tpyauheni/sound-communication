import time
import threading

from log import LOGGER


class Stream:
    def can_read(self) -> bool:
        raise NotImplementedError('not implemented')

    def read(self, length: int, block: bool = True, precision: float = 0.05) -> bytes:
        raise NotImplementedError('not implemented')

    def can_write(self) -> bool:
        raise NotImplementedError('not implemented')

    def write(self, data: bytes, block: bool = True, precision: float = 0.05) -> None:
        raise NotImplementedError('not implemented')


# Must only be used in one thread (but another thread may write to `input_buffer` considering `input_lock` or pop from `output_buffer` considering `output_lock`).
class BufferedStream(Stream):
    input_buffer: bytes
    input_lock: threading.Lock
    output_buffer: list[bytes] = []
    output_lock: threading.Lock
    _turn_write: bool

    def __init__(self, turn_write: bool) -> None:
        self.input_buffer = bytes()
        self.input_lock = threading.Lock()
        self.output_buffer = []
        self.output_lock = threading.Lock()
        self._turn_write = turn_write

    def turn(self) -> None:
        with self.input_lock:
            with self.output_lock:
                self._turn_write = not self._turn_write

    def turn_read(self) -> None:
        if not self._turn_write:
            return

        with self.input_lock:
            with self.output_lock:
                self._turn_write = False

    def turn_write(self) -> None:
        if self._turn_write:
            return

        with self.input_lock:
            with self.output_lock:
                self._turn_write = True

    def can_read(self) -> bool:
        return not self._turn_write

    def read(self, length: int, block: bool = True, precision: float = 0.05) -> bytes:
        with self.input_lock:
            if length <= len(self.input_buffer):
                data: bytes = self.input_buffer[:length]
                self.input_buffer = self.input_buffer[length:]

                if len(self.input_buffer) > 0:
                    LOGGER.verbose_warning('There is remaining data in input buffer after read:', len(self.input_buffer))
                else:
                    LOGGER.ok('There is no remaining data in input buffer after data read')

                LOGGER.verbose_stream('Data was read:', data)
                return data

            if not block:
                data: bytes = self.input_buffer
                self.input_buffer = bytes()
                if len(data):
                    LOGGER.verbose_stream('Data was read (non-blocking):', data)
                return data

        while length > len(self.input_buffer):
            time.sleep(precision)

        with self.input_lock:
            data: bytes = self.input_buffer[:length]
            self.input_buffer = self.input_buffer[length:]

            if len(self.input_buffer) > 0:
                LOGGER.verbose_warning('There is remaining data in input buffer after read:', len(self.input_buffer))
            else:
                LOGGER.ok('There is no remaining data in input buffer after data read')

            if len(data):
                LOGGER.verbose_stream('Data was read (blocking):', data)
            return data

    def can_write(self) -> bool:
        return self._turn_write

    def write(self, data: bytes, block: bool = True, precision: float = 0.05) -> None:
        LOGGER.verbose_stream('Appending data:', data)
        self.output_buffer.append(data)
        LOGGER.verbose_stream('Total data:', self.output_buffer)

        if not block:
            return

        while len(self.output_buffer) > 0 or self.output_lock.locked():
            time.sleep(precision)

