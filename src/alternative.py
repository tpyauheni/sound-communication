from typing import Any

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

    def __init__(self, turn_write: bool) -> None:
        self.transformer = ggwave.init()
        self.ctx = pyaudio.PyAudio()
        self.input_stream = self.ctx.open(format=pyaudio.paFloat32, channels=1, rate=48_000, input=True, frames_per_buffer=1024)
        self.output_stream = self.ctx.open(format=pyaudio.paFloat32, channels=1, rate=48_000, output=True, frames_per_buffer=4096)
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
                if self.turn_write:
                    frames: int = self.input_stream.get_read_available()
                    self.input_stream.read(frames, exception_on_overflow=False)
                    time.sleep(0.01)
                    continue

                frame: bytes = self.input_stream.read(1024, exception_on_overflow=False)
                data: bytes | None = ggwave.decode(self.transformer, frame)

                if data:
                    with self.input_lock:
                        self.input_buffer += data
        except OSError as exc:
            print(exc)

    def _write_loop(self) -> None:
        while True:
            if not self.turn_write:
                time.sleep(0.01)

            if len(self.output_buffer) == 0:
                time.sleep(0.01)
                continue

            with self.output_lock:
                data: bytes = self.output_buffer.pop()
                self._write(data)

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


# It is a bitmask so next element must be the next power of two
SYN: int = 1
ACK: int = 2


def sender() -> None:
    if '--disable-log' in sys.argv:
        ggwave.disableLog()

    stream: AlternativeStream = AlternativeStream(True)

    while True:
        stream.clear_input_buffer()
        stream.write(struct.pack('<B', SYN))
        stream.turn()
        data: bytes = stream.read(1)
        stream.turn()

        if struct.unpack('<B', data)[0] != SYN | ACK:
            print('Another peer responded with something different than `SYN|ACK`')
            time.sleep(3.0)
            continue

        stream.write(struct.pack('<B', ACK))
        stream.turn()
        break

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

    while True:
        stream.clear_input_buffer()

        if struct.unpack('<B', stream.read(1))[0] != SYN:
            print('!SYN')
            continue

        stream.turn()
        stream.write(struct.pack('<B', SYN | ACK))
        stream.turn()

        if struct.unpack('<B', stream.read(1))[0] != ACK:
            print('Another peer responded with something different than `ACK`')
            time.sleep(3.0)
            continue

        # stream.write(struct.pack('<B', ACK))
        break

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

