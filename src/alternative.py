from typing import Any, final

import ggwave
import pyaudio
import threading
import time
import struct
import sys

import base64

from stream import BufferedStream
from cryptoec import KeyExchanger, SymmetricKey


class GgwObject:
    """
    That class is a workaround.
    """

    data: bytes

    def __init__(self, data: bytes) -> None:
        self.data = data

    def encode(self) -> bytes:
        return self.data


class AlternativeStream(BufferedStream):
    transformer: Any
    ctx: pyaudio.PyAudio
    input_stream: pyaudio.Stream
    output_stream: pyaudio.Stream
    input_lock: threading.Lock
    output_lock: threading.Lock
    reader: threading.Thread
    writer: threading.Thread
    output_chunk_bytes: int

    def __init__(self, turn_write: bool) -> None:
        self.transformer = ggwave.init()
        self.ctx = pyaudio.PyAudio()
        self.input_stream = self.ctx.open(format=pyaudio.paFloat32, channels=1, rate=48_000, input=True, frames_per_buffer=1024)
        self.output_chunk_bytes = 1024 * 4
        self.output_stream = self.ctx.open(format=pyaudio.paFloat32, channels=1, rate=48_000, output=True, frames_per_buffer=self.output_chunk_bytes // 4)
        self.input_lock = threading.Lock()
        self.output_lock = threading.Lock()
        self.reader = threading.Thread(target=self._read_loop)
        self.writer = threading.Thread(target=self._write_loop)
        super().__init__(turn_write)
        self.reader.start()
        self.writer.start()

    def _read_loop(self) -> None:
        try:
            while True:
                if self._turn_write:
                    frames: int = self.input_stream.get_read_available()
                    self.input_stream.read(frames, exception_on_overflow=False)
                    time.sleep(0.01)
                    continue

                frame: bytes = self.input_stream.read(1024, exception_on_overflow=False)
                data: bytes | None = ggwave.decode(self.transformer, frame)

                if data:
                    with self.input_lock:
                        # Sleep until another peer stops transmitting its message.
                        time.sleep(0.15)
                        self.input_buffer += data
        except OSError as exc:
            print(exc)

    def _try_write(self) -> bool:
        if not self._turn_write:
            return False

        if len(self.output_buffer) == 0:
            return False

        if self.output_lock.acquire(blocking=False):
            try:
                data: bytes = self.output_buffer.pop()
                self._write(data)
            finally:
                self.output_lock.release()

            return True

        return False

    def _write_loop(self) -> None:
        silence: bytes = b'\0' * self.output_chunk_bytes

        while True:
            self._try_write()
            self.output_stream.write(silence)

    def _write(self, data: bytes) -> None:
        frames: bytes = ggwave.encode(GgwObject(data), protocolId=5, volume=100)
        self.output_stream.write(frames, len(frames) // 4)

    def clear_input_buffer(self) -> None:
        with self.input_lock:
            self.input_buffer = bytes()

    def clear_output_buffer(self) -> None:
        with self.output_lock:
            self.output_buffer.clear()

    def dispose(self) -> None:
        self.input_stream.stop_stream()
        self.input_stream.close()
        self.output_stream.stop_stream()
        self.output_stream.close()
        self.ctx.terminate()


class ReliableTransceiver:
    # It is a bitmask so next element must be the next power of two
    # Synchronize (from TCP)
    SYN: int = 1
    # Acknowledged (from TCP)
    ACK: int = 2
    # Retry (unused)
    RTR: int = 4

    session_started: bool = False
    last_received_packet: int = -1
    last_sent_packet: int = -1

    stream: AlternativeStream

    def __init__(self, stream: AlternativeStream) -> None:
        self.stream = stream

    def read_equals(self, timeout: float, data: bytes, precision: float = 0.01) -> bool:
        size: int = len(data)
        start_time: float = time.time()
        result: bytes = bytes()
        self.stream.turn_read()

        while True:
            time_now: float = time.time()

            if time_now >= start_time + timeout:
                return False

            buffer: bytes = self.stream.read(size, block=False)
            result += buffer

            if len(result) > size:
                return False

            if len(result) == size:
                if result == data:
                    return True

                print(f'Buffer {result} != buffer {data}')
                return False

            time.sleep(precision)

    def read(
            self,
            size: int,
            abort_timeout: float = 15.0,
            send_ack: bool = True,
            precision: float = 0.01,
    ) -> bytes | tuple[bytes, bytes]:
        if size <= 0:
            raise ValueError('Attempted to read data with non-positive size from a stream')

        self.last_received_packet += 1

        start_time: float = time.time()
        result: bytes = bytes()
        self.stream.turn_read()

        while True:
            time_now: float = time.time()

            if time_now - start_time >= abort_timeout:
                # TODO: Reset everything and try to connect from the very beginning again
                raise ConnectionAbortedError()

            buffer: bytes = self.stream.read(1, block=False)

            if len(buffer) == 0:
                time.sleep(precision)
                continue

            if len(buffer) > 1:
                print('[Warning] Read more bytes from buffer than expected')

            batch_id: int = struct.unpack('<B', buffer)[0]

            if len(buffer) >= 1:
                if batch_id > self.last_received_packet:
                    print(f'[Warning] Received packet with unexpected id: {batch_id}, expected {self.last_received_packet}')
                    # TODO: Properly ensure that we are fully discarding that packet
                    time.sleep(0.5)
                    raise ConnectionAbortedError()
                    # time.sleep(0.5)
                    # start_time += 0.5
                    # self.stream.clear_input_buffer()
                    # continue

                if batch_id < self.last_received_packet:
                    # TODO: Properly ensure that we are fully discarding that packet
                    time.sleep(0.5)
                    start_time += 0.5
                    self.stream.clear_input_buffer()
                    # We are sending ACK even if `send_ack` is False as it only determines
                    # such behavior if `batch_id` == `self.last_received_packet`.
                    self.stream.turn_write()
                    self.stream.write(struct.pack('<BB', batch_id, self.ACK))
                    self.stream.turn_read()
                    continue

                break

        ack_packet: bytes = struct.pack('<BB', batch_id, self.ACK)

        while size > 0:
            time_now: float = time.time()

            if time_now - start_time >= abort_timeout:
                # TODO: Reset everything and try to connect from the very beginning again
                raise ConnectionAbortedError()

            buffer: bytes = self.stream.read(size, block=False)
            result += buffer
            size -= len(buffer)

            if size < 0:
                print('Returning more bytes that requested!')

            if size <= 0:
                if send_ack:
                    self.stream.turn_write()
                    self.stream.write(ack_packet)
                    self.stream.turn_read()
                break

            time.sleep(precision)

        if send_ack:
            return result

        print(ack_packet, result, type(ack_packet), type(result))
        return ack_packet, result

    def write(self, data: bytes, resend_timeout: float = 1.0, abort_retries: int = 5, precision: float = 0.01) -> None:
        self.last_sent_packet += 1
        self.last_sent_packet %= 256
        full_data: bytes = struct.pack('<B', self.last_sent_packet) + data
        self.stream.turn_write()
        self.stream.write(full_data)

        size: int = 2
        last_resend_time: float = time.time()
        result: bytes = bytes()
        retries: int = 0

        while True:
            time_now: float = time.time()

            if time_now - last_resend_time >= resend_timeout:
                self.stream.turn_write()
                self.stream.write(full_data)
                retries += 1

                if retries >= abort_retries:
                    # TODO: Reset everything and try to connect from the very beginning again
                    raise ConnectionAbortedError()

                last_resend_time = time.time()

            self.stream.turn_read()
            buffer: bytes = self.stream.read(size, block=False)
            result += buffer
            size -= len(buffer)

            if size <= 0:
                if size < 0:
                    print('Returning more bytes that requested!')
                    break

                response: tuple[int, int] = struct.unpack('<BB', result)
                failure: bool = False

                if response[1] != self.ACK:
                    print('[Warning] Received non-ACK response code:', response)
                    failure = True

                if response[0] != self.last_sent_packet:
                    print(f'[Warning] Received ACK for different packet ({response[0]}) but sent {self.last_sent_packet}')
                    failure = True

                if failure:
                    self.stream.turn_write()
                    self.stream.write(full_data)
                    retries += 1

                    if retries >= abort_retries:
                        # TODO: Reset everything and try to connect from the very beginning again
                        raise ConnectionAbortedError()

                    last_resend_time = time.time()
                else:
                    return

            time.sleep(precision)

    def connect_init_sender(self, reconnect_interval: float = 1.5) -> None:
        # self.stream.clear_input_buff= er()
        #
        # if is_sender:
        #     self.stream.turn_write()
        #     self.stream.write(struct.pack('<B', self.SYN))
        while True:
            self.stream.clear_input_buffer()
            self.stream.clear_output_buffer()
            self.last_sent_packet = -1
            self.last_received_packet = -1
            self.stream.turn_write()

            retries: int = 3

            while retries >= 0:
                print('Iter with retries', retries)
                self.stream.turn_write()
                self.stream.write(struct.pack('<B', self.SYN))
                print('Sent `SYN`')
                self.stream.turn_read()

                try:
                    ack, data = self.read(1, abort_timeout=2.5, send_ack=False)
                except ConnectionAbortedError:
                    print('Connection aborted')
                    retries = -1
                    break

                assert isinstance(ack, bytes)
                assert isinstance(data, bytes)
                # print(data)
                response: int = struct.unpack('<B', data)[0]

                if response != self.SYN | self.ACK:
                    print('Another peer responded with something different than `SYN|ACK`:', response)
                    time.sleep(reconnect_interval)
                    retries -= 1
                    print('Retries:', retries)
                    continue

                print('Got `SYN|ACK`')
                self.stream.turn_write()
                self.stream.write(ack)
                print('Sent `ACK`')
                break

            if retries >= 0:
                break

    def connect_init_receiver(self, reconnect_interval: float = 1.0) -> None:
        while True:
            self.stream.clear_input_buffer()
            self.stream.clear_output_buffer()
            self.last_sent_packet = -1
            self.last_received_packet = -1
            self.stream.turn_read()

            buffer: bytes = self.stream.read(1)

            if struct.unpack('<B', buffer)[0] != self.SYN:
                print('[Warning] Got value different from `SYN`')
                continue

            print('Received `SYN`, sending `SYN|ACK`...')

            retries: int = 3
            self.last_sent_packet += 1
            syn_ack: bytes = struct.pack('<BB', self.last_sent_packet, self.SYN | self.ACK)

            while retries >= 0:
                self.stream.turn_write()
                self.stream.write(syn_ack)
                print('Sent `SYN|ACK`')
                self.stream.turn_read()

                if self.read_equals(reconnect_interval, struct.pack('<BB', self.last_sent_packet, self.ACK)):
                    print('Received `ACK`')
                    break

                retries -= 1

            if retries >= 0:
                break

    def key_exchange_sender(self) -> None:
        key_exchanger: KeyExchanger = KeyExchanger(None, None)
        key: bytes = key_exchanger.exchange_pubkey()
        print('Sending key: ', key)
        self.write(key)
        print('Sent that key')
        their_pubkey: bytes = self.read(32)
        print('My public key: ', key_exchanger.pubkey())
        print('Their public key: ', their_pubkey)
        print('My secret key: ', key_exchanger.seckey())
        session_key: SymmetricKey = key_exchanger.get_symkey(their_pubkey)
        print('Session key: ', session_key.key_ref()[0])

        ciphertext: bytes = session_key.encrypt(b'Hello')
        print('Sending cipher: ', ciphertext)
        self.write(ciphertext)

        # Encrypted Client Hello
        ech: bytes = self.read(8 + 2)
        decrypted: bytes = session_key.decrypt(ech)
        assert decrypted == b'Hi'

        ciphertext = session_key.encrypt(struct.pack('<B', self.ACK))
        print('Sending cipher: ', ciphertext)
        self.write(ciphertext)

        print('Connection established')

        # TODO

        session_key.dispose()
        self.stream.dispose()
        print('Connection finished')

    def key_exchange_receiver(self) -> None:
        key_exchanger: KeyExchanger = KeyExchanger(None, None)
        their_pubkey: bytes = self.read(32)
        print('Their public key: ', their_pubkey)
        session_key: SymmetricKey = key_exchanger.get_symkey(their_pubkey, dispose=False)
        print('My public key: ', key_exchanger.pubkey())
        print('My secret key: ', key_exchanger.seckey())
        print('Session key: ', session_key.key_ref()[0])
        key: bytes = key_exchanger.exchange_pubkey()
        print('Sender\'s key: ', key)
        self.write(key)
        print('Sent key', flush=True)

        # Encrypted Client Hello
        print('Reading ECH')
        ech: bytes = self.read(8 + 5)
        decrypted: bytes = session_key.decrypt(ech)
        assert decrypted == b'Hello'

        ciphertext: bytes = session_key.encrypt(b'Hi')
        print('Sending cipher: ', ciphertext)
        self.write(ciphertext)

        print('did that')
        print('almost there', flush=True)
        plaintext: bytes = session_key.decrypt(self.read(8 + 1))
        print('Should be ACK:', plaintext)
        assert struct.unpack('<B', plaintext)[0] == self.ACK

        print('Connection established')

        # TODO

        session_key.dispose()
        self.stream.dispose()
        print('Connection finished')

    def connect(self, is_sender: bool) -> None:
        while True:
            print(f'Connecting as {['receiver', 'sender'][is_sender]}...')
            (self.connect_init_sender if is_sender else self.connect_init_receiver)()
            print('Initial (unencrypted) connection established, exchanging keys...')
            (self.key_exchange_sender if is_sender else self.key_exchange_receiver)()

            try:
                self.read(1)
            except ConnectionAbortedError:
                print('Disconnected')
                continue

            time.sleep(15.0)
            print('Disconnected: idle time exceeded')


def sender() -> None:
    if '--disable-log' in sys.argv:
        ggwave.disableLog()

    stream: AlternativeStream = AlternativeStream(True)
    transceiver: ReliableTransceiver = ReliableTransceiver(stream)
    transceiver.connect(True)
    return

    print('Initialization sequence complete, exchanging keys...')
    key_exchanger: KeyExchanger = KeyExchanger(None, None)
    their_pubkey: bytes = stream.read(32)
    print('Their public key: ', their_pubkey)
    session_key: SymmetricKey = key_exchanger.get_symkey(their_pubkey, dispose=False)
    print('My public key: ', key_exchanger.pubkey())
    print('My secret key: ', key_exchanger.seckey())
    print('Session key: ', session_key.key_ref()[0])
    stream.turn()
    key: bytes = key_exchanger.exchange_pubkey()
    print('Sender\'s key: ', key)
    stream.write(key)
    print('Sent key', flush=True)

    stream.turn()
    # Encrypted Client Hello
    print('Reading ECH')
    ech: bytes = stream.read(8 + 5)
    decrypted: bytes = session_key.decrypt(ech)
    assert decrypted == b'Hello'

    stream.turn()
    ciphertext: bytes = session_key.encrypt(b'Hi')
    print('Sending cipher: ', ciphertext)
    stream.write(ciphertext)

    print('did that')
    stream.turn()
    print('almost there', flush=True)
    plaintext: bytes = session_key.decrypt(stream.read(8 + 1))
    print('Should be ACK:', plaintext)
    assert struct.unpack('<B', plaintext)[0] == ACK

    print('Connection established')

    # TODO

    session_key.dispose()
    stream.dispose()
    print('Connection finished')

    # print('Enter string to transfer:', flush=True)
    # str_to_transfer: str = input()

    # waveform = ggwave.encode(str_to_transfer, protocolId = 5, volume = 100)

    # stream.write(waveform, len(waveform)//4)
    # stream.stop_stream()
    # stream.close()
    # p.terminate()
    # print('Done', flush=True)


def receiver() -> None:
    if '--disable-log' in sys.argv:
        ggwave.disableLog()

    stream: AlternativeStream = AlternativeStream(False)
    transceiver: ReliableTransceiver = ReliableTransceiver(stream)
    transceiver.connect(False)
    return

    stream.turn()
    print('Initialization sequence complete, exchanging keys...')
    key_exchanger: KeyExchanger = KeyExchanger(None, None)
    key: bytes = key_exchanger.exchange_pubkey()
    print('Sending key: ', key)
    stream.write(key)
    print('Sent that key')
    stream.turn()
    print('After turn')
    their_pubkey: bytes = stream.read(32)
    print('My public key: ', key_exchanger.pubkey())
    print('Their public key: ', their_pubkey)
    print('My secret key: ', key_exchanger.seckey())
    session_key: SymmetricKey = key_exchanger.get_symkey(their_pubkey)
    print('Session key: ', session_key.key_ref()[0])

    stream.turn()
    ciphertext: bytes = session_key.encrypt(b'Hello')
    print('Sending cipher: ', ciphertext)
    stream.write(ciphertext)

    stream.turn()
    # Encrypted Client Hello
    ech: bytes = stream.read(8 + 2)
    decrypted: bytes = session_key.decrypt(ech)
    assert decrypted == b'Hi'

    stream.turn()
    ciphertext = session_key.encrypt(struct.pack('<B', ACK))
    print('Sending cipher: ', ciphertext)
    stream.write(ciphertext)

    print('Connection established')

    # TODO

    session_key.dispose()
    stream.dispose()
    print('Connection finished')

    # p = pyaudio.PyAudio()

    # stream = p.open(format=pyaudio.paFloat32, channels=1, rate=48000, input=True, frames_per_buffer=1024)

    # print('Listening ... Press Ctrl+C to stop', flush=True)
    # instance = ggwave.init()
    #
    # try:
    #     while True:
    #         data = stream.read(1024, exception_on_overflow=False)
    #         res = ggwave.decode(instance, data)
    #         if (not res is None):
    #             try:
    #                 print('Received text: ' + res.decode("utf-8"), flush=True)
    #             except:
    #                 pass
    # except KeyboardInterrupt:
    #     pass
    #
    # ggwave.free(instance)
    #
    # stream.stop_stream()
    # stream.close()
    #
    # p.terminate()

