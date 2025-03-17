import time
import threading


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
    turn_write: bool

    def __init__(self, turn_write: bool) -> None:
        self.input_buffer = bytes()
        self.input_lock = threading.Lock()
        self.output_buffer = []
        self.output_lock = threading.Lock()
        self.turn_write = turn_write

    def turn(self) -> None:
        with self.input_lock:
            with self.output_lock:
                self.turn_write = not self.turn_write

    def can_read(self) -> bool:
        return not self.turn_write

    def read(self, length: int, block: bool = True, precision: float = 0.05) -> bytes:
        with self.input_lock:
            if length <= len(self.input_buffer):
                data: bytes = self.input_buffer[:length]
                self.input_buffer = self.input_buffer[length:]
                if len(self.input_buffer) > 0:
                    print('There is remaining data in input buffer after read:', len(self.input_buffer))
                return data

            if not block:
                data: bytes = self.input_buffer
                self.input_buffer = bytes()
                return data

        while length > len(self.input_buffer):
            time.sleep(precision)

        with self.input_lock:
            data: bytes = self.input_buffer[:length]
            self.input_buffer = self.input_buffer[length:]
            if len(self.input_buffer) > 0:
                print('There is remaining data in input buffer after read:', len(self.input_buffer))
            return data

    def can_write(self) -> bool:
        return self.turn_write

    def write(self, data: bytes, block: bool = True, precision: float = 0.05) -> None:
        self.output_buffer.append(data)

        if not block:
            return

        while len(self.output_buffer) > 0 or self.output_lock.locked():
            time.sleep(precision)

