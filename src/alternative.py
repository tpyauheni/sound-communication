from typing import Any

from pyggwave import GGWave, Parameters, OperatingMode, Protocol
import pyggwave
import pyaudio
import threading
import time
import struct
import sys
import ctypes
import base64

from error_corrector import REDUNDANCY_SIZE, ErrorCorrector
from log import LOGGER
from stream import BufferedStream
from cryptoec import KeyExchanger, SymmetricKey
from ui import UIProcessor


class AlternativeStream(BufferedStream):
    SEND_INIT_INTERVAL: float = 1.0
    SEND_INTERVAL_SENDER: tuple[float, float] = 0.2, 0.3
    SEND_INTERVAL_RECEIVER: tuple[float, float] = 0.7, 0.8
    MAX_RECEIVING_TIME: float = 6.0

    transformer: GGWave
    ctx: pyaudio.PyAudio
    input_stream: pyaudio.Stream
    output_stream: pyaudio.Stream
    input_lock: threading.Lock
    output_lock: threading.Lock
    reader: threading.Thread
    writer: threading.Thread
    output_chunk_bytes: int
    protocol: Protocol = Protocol.ULTRASOUND_FASTEST
    first_packet_time: float | None = None
    send_interval: tuple[float, float]
    receiving_start: float | None = None

    def _libasound_error_handler(self, filename: bytes, line: bytes, function: bytes, err: int, fmt: bytes, *args) -> None:
        LOGGER.error_pyaudio('libasound:', f'{filename.decode()}:{line}:', f'{function.decode()}', err, fmt.decode().replace('%s', '?'))

    def __init__(self, turn_write: bool, fake: bool = False) -> None:
        if fake:
            return

        for i in range(9):
            GGWave.rx_toggle_protocol(Protocol(i), False)
            GGWave.tx_toggle_protocol(Protocol(i), False)

        GGWave.rx_toggle_protocol(self.protocol, True)
        GGWave.tx_toggle_protocol(self.protocol, True)

        self.transformer = GGWave(
            Parameters(
                operating_mode=OperatingMode.RX_AND_TX.value,
            ),
        )

        ERROR_HANDLER_FUNC = ctypes.CFUNCTYPE(
            None,
            ctypes.c_char_p,
            ctypes.c_int,
            ctypes.c_char_p,
            ctypes.c_int,
            ctypes.c_char_p,
        )

        c_error_handler = ERROR_HANDLER_FUNC(self._libasound_error_handler)

        asound = ctypes.cdll.LoadLibrary('libasound.so')
        # Set error handler
        asound.snd_lib_error_set_handler(c_error_handler)
        self.ctx = pyaudio.PyAudio()
        asound.snd_lib_error_set_handler(None)

        self.input_stream = self.ctx.open(format=pyaudio.paFloat32, channels=1, rate=48_000, input=True, frames_per_buffer=1024)
        self.output_chunk_bytes = 1024 * 4
        self.output_stream = self.ctx.open(format=pyaudio.paFloat32, channels=1, rate=48_000, output=True, frames_per_buffer=self.output_chunk_bytes // 4)
        self.input_lock = threading.Lock()
        self.output_lock = threading.Lock()
        self.reader = threading.Thread(target=self._read_loop)
        self.writer = threading.Thread(target=self._write_loop)

        if turn_write:
            self.send_interval = self.SEND_INTERVAL_SENDER
        else:
            self.send_interval = self.SEND_INTERVAL_RECEIVER

        super().__init__(turn_write)
        self.reader.start()
        self.writer.start()

    def _decode_data(self, data: bytes) -> bytes:
        LOGGER.verbose_coder('Original data before decoding:', data)
        decoded: bytes = ErrorCorrector(data).decode()
        LOGGER.verbose_coder('Decoded data:', decoded)
        return decoded

    def _encode_data(self, data: bytes) -> bytes:
        LOGGER.verbose_coder('Original data before encoding:', data)
        encoded: bytes = ErrorCorrector(data).encode()
        LOGGER.verbose_coder('Encoded data:', encoded)
        return encoded

    def _read_loop(self) -> None:
        try:
            while True:
                if self._turn_write:
                    if self.transformer.rx_receiving():
                        pyggwave.raw__rx_stop_receiving(self.transformer.instance)
                    frames: int = self.input_stream.get_read_available()
                    self.input_stream.read(frames, exception_on_overflow=False)
                    time.sleep(0.01)
                    continue

                frame: bytes = self.input_stream.read(1024, exception_on_overflow=False)
                data: bytes | None = self.transformer.decode(frame)

                if data:
                    LOGGER.verbose_frame('Received data:', data)

                    with self.input_lock:
                        # Sleep until another peer stops transmitting its message.
                        time.sleep(0.15)
                        self.input_buffer += self._decode_data(data)
        except OSError as exc:
            LOGGER.error3(exc)

    def _try_write(self) -> bool:
        if self.transformer.rx_receiving():
            if self.receiving_start is None:
                self.receiving_start = time.time()

            delta_time: float = time.time() - self.receiving_start

            if delta_time > self.MAX_RECEIVING_TIME:
                # self.transformer.rx_stop_receiving()
                pyggwave.raw__rx_stop_receiving(self.transformer.instance)
                self.receiving_start = None
                LOGGER.verbose('Stopped receiving')
                # print(f'{time.time():.2f}', 'Stopped receiving')
                return False

            # print(f'{time.time():.2f}', f'Skipping write turn: receiving: {self.receiving_start:.2f}, {delta_time:.2f}')
            return False

        if self.first_packet_time is not None:
            delta_time = time.time() - self.first_packet_time
            interval_start, interval_end = self.send_interval
            interval_point: float = delta_time % self.SEND_INIT_INTERVAL

            if interval_point < interval_start or interval_point > interval_end:
                # print(f'{time.time():.2f}', f'Skipping write turn: interval point {interval_point:.2f} is not on interval [{interval_start:.2f}; {interval_end:.2f}]')
                return False

            # print(f'{time.time():.2f}', f'Went through initial checks: {interval_point:.2f} [{interval_start:.2f}; {interval_end:.2f}]')

        if not self._turn_write:
            # print(f'{time.time():.2f}', 'Skipping write turn: not write turn')
            return False

        if len(self.output_buffer) == 0:
            # print(f'{time.time():.2f}', 'Skipping write turn: output buffer empty')
            return False

        if self.output_lock.acquire(blocking=False):
            try:
                data: bytes = self.output_buffer.pop()
                self._write(self._encode_data(data))
            finally:
                self.output_lock.release()

            return True

        return False

    def _write_loop(self) -> None:
        silence: bytes = b'\0' * self.output_chunk_bytes

        while True:
            if not self._try_write():
                self.output_stream.write(silence)

    def _write(self, data: bytes) -> None:
        LOGGER.verbose_frame('Writing data:', data)
        frames: bytes = self.transformer.encode(data, protocol=self.protocol, volume=100)
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

    last_received_packet: int = -1
    last_sent_packet: int = -1
    prev_packet_time: float | None = None
    first_packet_time: float | None = None
    session_key: SymmetricKey

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

                LOGGER.warning(f'Buffer {result} (received) != buffer {data} (expected)')
                return False

            time.sleep(precision)

    def read_insecure(
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

            LOGGER.verbose('Reading data with size 1')
            buffer: bytes = self.stream.read(1, block=False)
            LOGGER.verbose('Received data:', buffer)

            if len(buffer) == 0:
                time.sleep(precision)
                continue

            if len(buffer) > 1:
                LOGGER.warning('Read more bytes from buffer than expected')

            batch_id: int = struct.unpack('<B', buffer)[0]

            if len(buffer) >= 1:
                if batch_id > self.last_received_packet:
                    LOGGER.warning(f'Received packet with unexpected id: {batch_id}, expected {self.last_received_packet}')
                    # TODO: Properly ensure that we are fully discarding that packet
                    time.sleep(1.0)
                    raise ConnectionAbortedError()
                    # time.sleep(0.5)
                    # start_time += 0.5
                    # self.stream.clear_input_buffer()
                    # continue

                if batch_id < self.last_received_packet:
                    LOGGER.warning(f'Already ACK-ed packet received', batch_id, self.last_received_packet)
                    # TODO: Properly ensure that we are fully discarding that packet
                    time.sleep(1.0)
                    start_time += 1.0
                    self.stream.clear_input_buffer()
                    # We are sending ACK even if `send_ack` is False as it only determines
                    # such behavior if `batch_id` == `self.last_received_packet`.
                    self.stream.turn_write()
                    LOGGER.verbose('Responding with ACK to packet', batch_id)
                    self.stream.write(struct.pack('<BB', batch_id, self.ACK))
                    LOGGER.verbose('Done')
                    self.stream.turn_read()
                    continue

                break

        ack_packet: bytes = struct.pack('<BB', batch_id, self.ACK)

        while size > 0:
            LOGGER.debug('Trying to read data with size', size)
            time_now: float = time.time()

            if time_now - start_time >= abort_timeout:
                # TODO: Reset everything and try to connect from the very beginning again
                raise ConnectionAbortedError()

            LOGGER.verbose('Receiving packet')
            buffer: bytes = self.stream.read(size, block=False)
            LOGGER.verbose('Done')
            result += buffer
            size -= len(buffer)

            if size < 0:
                LOGGER.verbose('Returning more bytes that requested!')

            if size <= 0:
                if send_ack:
                    self.stream.turn_write()
                    LOGGER.verbose('Responding to received data with ACK')
                    self.stream.write(ack_packet)
                    LOGGER.verbose('Done')
                    self.stream.turn_read()
                break

            time.sleep(precision)

        LOGGER.debug('Done data read')

        if send_ack:
            return result

        return ack_packet, result

    def write_insecure(self, data: bytes, resend_timeout: float = 3.0, abort_retries: int = 5, precision: float = 0.01) -> None:
        LOGGER.verbose('Sending chunk:', data)
        self.last_sent_packet += 1
        self.last_sent_packet %= 256
        full_data: bytes = struct.pack('<B', self.last_sent_packet) + data
        self.stream.turn_write()
        LOGGER.verbose('Exact data:', full_data)
        self.stream.write(full_data)
        LOGGER.verbose('Sent data')

        size: int = 2
        last_resend_time: float = time.time()
        result: bytes = bytes()
        retries: int = 0

        while True:
            time_now: float = time.time()

            if time_now - last_resend_time >= resend_timeout:
                self.stream.turn_write()
                LOGGER.info('Resending data:', full_data)
                self.stream.write(full_data)
                LOGGER.verbose('Data was resent')
                retries += 1

                if retries >= abort_retries:
                    # TODO: Reset everything and try to connect from the very beginning again
                    raise ConnectionAbortedError()

                last_resend_time = time.time()

            self.stream.turn_read()
            LOGGER.verbose(f'Waiting for confirmation ({size})...')
            buffer: bytes = self.stream.read(size, block=False)
            result += buffer
            size -= len(buffer)

            if size <= 0:
                LOGGER.verbose('Got confirmation:', result)

                if size < 0:
                    LOGGER.error('Returning more bytes that requested!')
                    break

                response: tuple[int, int] = struct.unpack('<BB', result)
                failure: bool = False

                if response[1] != self.ACK:
                    LOGGER.warning('Received non-ACK response code:', response)
                    failure = True

                if response[0] != self.last_sent_packet:
                    LOGGER.warning(f'Received ACK for different packet ({response[0]} but {self.last_sent_packet} was sent)')
                    failure = True

                if failure:
                    self.stream.turn_write()
                    LOGGER.info(f'Resending data on failure:', full_data)
                    self.stream.write(full_data)
                    LOGGER.verbose('Resent data')
                    retries += 1

                    if retries >= abort_retries:
                        # TODO: Reset everything and try to connect from the very beginning again
                        raise ConnectionAbortedError()

                    last_resend_time = time.time()
                else:
                    return

            time.sleep(precision)

    def send(self, orig_data: bytes, chunk_size_max: int = 140) -> None:
        encrypted_data: bytes = self.session_key.encrypt(orig_data)
        len_data = struct.pack('<I', len(encrypted_data))
        LOGGER.verbose('Sending data; original data:')
        encrypted_data: bytes = len_data + encrypted_data
        LOGGER.verbose('Encrypted:', encrypted_data)

        data_chunks: list[bytes] = []
        data_left: bytes = encrypted_data
        nonce_size: int = 8
        chunk_size: int = chunk_size_max - nonce_size - REDUNDANCY_SIZE

        while len(data_left) >= chunk_size:
            data_chunks.append(data_left[:chunk_size])
            data_left = data_left[chunk_size:]

        if len(data_left) > 0:
            data_chunks.append(data_left)

        LOGGER.verbose('Data chunks:', data_chunks)

        for chunk in data_chunks:
            self.write_insecure(chunk)

    def receive(self, chunk_size: int = 140 - 14, timeout: float = 600.0, precision: float = 0.01) -> bytes:
        start_time: float = time.time()

        while len(self.stream.input_buffer) < 12:
            time.sleep(precision)

            if time.time() - start_time >= timeout:
                raise ConnectionAbortedError()

        data = self.read_insecure(min(len(self.stream.input_buffer) - 1, chunk_size), timeout - time.time() + start_time)
        LOGGER.verbose('Received data:', data)
        size = struct.unpack('<I', data[:4])[0]
        LOGGER.debug('Determined size of next data chunk:', size)
        cipher_buffer: bytes = data[4:]
        left_size: int = size - len(cipher_buffer)

        while left_size > 0:
            cipher_data: bytes = self.read_insecure(min(left_size, chunk_size), timeout - time.time() + start_time)
            cipher_buffer += cipher_data
            left_size -= len(cipher_data)

        LOGGER.verbose('Cipher buffer', cipher_buffer)
        data: bytes = self.session_key.decrypt(cipher_buffer)
        LOGGER.verbose('Decrypted to:', data)
        return data

    def connect_init_sender(self, reconnect_interval: float = 1.5) -> None:
        while True:
            self.stream.clear_input_buffer()
            self.stream.clear_output_buffer()
            self.last_sent_packet = -1
            self.last_received_packet = -1
            self.prev_packet_time = None
            self.first_packet_time = None
            self.stream.turn_write()

            retries: int = 3

            while retries >= 0:
                self.prev_packet_time = time.time()
                self.stream.turn_write()
                self.stream.write(struct.pack('<B', self.SYN))
                LOGGER.info('Sent `SYN`')
                self.stream.turn_read()

                try:
                    ack, data = self.read_insecure(1, abort_timeout=2.5, send_ack=False)
                except ConnectionAbortedError:
                    LOGGER.info('Connection aborted')
                    retries = -1
                    break

                assert isinstance(ack, bytes)
                assert isinstance(data, bytes)
                response: int = struct.unpack('<B', data)[0]

                if response != self.SYN | self.ACK:
                    LOGGER.warning('Another peer responded with something different than `SYN|ACK`:', response)
                    time.sleep(reconnect_interval)
                    retries -= 1
                    continue

                LOGGER.info('Got `SYN|ACK`')
                self.first_packet_time = self.prev_packet_time
                self.stream.first_packet_time = self.first_packet_time
                self.stream.turn_write()
                self.stream.write(ack)
                LOGGER.info('Sent `ACK`')
                break

            if retries >= 0:
                break

    def connect_init_receiver(self, reconnect_interval: float = 1.0) -> None:
        while True:
            self.stream.clear_input_buffer()
            self.stream.clear_output_buffer()
            self.last_sent_packet = -1
            self.last_received_packet = -1
            self.prev_packet_time = None
            self.first_packet_time = None
            self.stream.turn_read()

            buffer: bytes = self.stream.read(1)

            if struct.unpack('<B', buffer)[0] != self.SYN:
                LOGGER.warning('Got value different from `SYN`')
                continue

            self.prev_packet_time = time.time()
            LOGGER.info('Received `SYN`, sending `SYN|ACK`...')

            retries: int = 3
            self.last_sent_packet += 1
            syn_ack: bytes = struct.pack('<BB', self.last_sent_packet, self.SYN | self.ACK)

            while retries >= 0:
                self.stream.turn_write()
                self.stream.write(syn_ack)
                LOGGER.info('Sent `SYN|ACK`')
                self.stream.turn_read()

                if self.read_equals(reconnect_interval, struct.pack('<BB', self.last_sent_packet, self.ACK)):
                    self.first_packet_time = self.prev_packet_time
                    self.stream.first_packet_time = self.first_packet_time
                    LOGGER.info('Received `ACK`')
                    break

                retries -= 1

            if retries >= 0:
                break

    def key_exchange_sender(self) -> None:
        key_exchanger: KeyExchanger = KeyExchanger(None, None)
        key: bytes = key_exchanger.exchange_pubkey()
        self.write_insecure(key)
        their_pubkey: bytes = self.read_insecure(32)
        LOGGER.info('My public key: "', base64.b85encode(key_exchanger.pubkey()).decode(), '"', sep='')
        LOGGER.info('Their public key: "', base64.b85encode(their_pubkey).decode(), '"', sep='')
        self.session_key: SymmetricKey = key_exchanger.get_symkey(their_pubkey)

        ciphertext: bytes = self.session_key.encrypt(b'Hello')
        LOGGER.verbose('Sending cipher: ', ciphertext)
        self.write_insecure(ciphertext)

        # Encrypted Client Hello
        ech: bytes = self.read_insecure(8 + 2)
        decrypted: bytes = self.session_key.decrypt(ech)
        assert decrypted == b'Hi'

        ciphertext = self.session_key.encrypt(struct.pack('<B', self.ACK))
        LOGGER.verbose('Sending cipher: ', ciphertext)
        self.write_insecure(ciphertext)

        LOGGER.info('Connection established')

        self.session_start()

        self.session_key.dispose()
        LOGGER.info('Connection finished')

    def key_exchange_receiver(self) -> None:
        key_exchanger: KeyExchanger = KeyExchanger(None, None)
        their_pubkey: bytes = self.read_insecure(32)
        LOGGER.info('Their public key: "', base64.b85encode(their_pubkey).decode(), '"', sep='')
        self.session_key: SymmetricKey = key_exchanger.get_symkey(their_pubkey, dispose=False)
        LOGGER.info('My public key: "', base64.b85encode(key_exchanger.pubkey()).decode(), '"', sep='')
        key: bytes = key_exchanger.exchange_pubkey()
        self.write_insecure(key)

        # Encrypted Client Hello
        LOGGER.verbose('Reading ECH')
        ech: bytes = self.read_insecure(8 + 5)
        decrypted: bytes = self.session_key.decrypt(ech)
        assert decrypted == b'Hello'

        ciphertext: bytes = self.session_key.encrypt(b'Hi')
        LOGGER.verbose('Sending cipher: ', ciphertext)
        self.write_insecure(ciphertext)

        plaintext: bytes = self.session_key.decrypt(self.read_insecure(8 + 1))
        LOGGER.verbose('Should be ACK:', plaintext)
        assert struct.unpack('<B', plaintext)[0] == self.ACK

        LOGGER.info('Connection established')

        self.session_start()

        self.session_key.dispose()
        LOGGER.info('Connection finished')

    def session_start(self) -> None:
        ui: UIProcessor = UIProcessor(self)
        ui.run()

    def connect(self, is_sender: bool) -> None:
        while True:
            LOGGER.info(f'Connecting as {['receiver', 'sender'][is_sender]}...')
            (self.connect_init_sender if is_sender else self.connect_init_receiver)()
            LOGGER.info('Initial (unencrypted) connection established, exchanging keys...')
            (self.key_exchange_sender if is_sender else self.key_exchange_receiver)()

            try:
                self.read_insecure(1)
            except ConnectionAbortedError:
                LOGGER.info('Disconnected')
                continue

            time.sleep(15.0)
            LOGGER.info('Disconnected: idle time exceeded')


def sender() -> None:
    if '--disable-log' in sys.argv:
        GGWave.disable_log()
        LOGGER.log_tags = ['I', 'W', 'E1']
        LOGGER.traceback_tags = LOGGER.LOG_NOTHING

    LOGGER.add_global_prefix('Sender')
    stream: AlternativeStream = AlternativeStream(True)
    transceiver: ReliableTransceiver = ReliableTransceiver(stream)
    # transceiver.session_key = SymmetricKey(b'tUH\x19\x9d\x8bZK\xd0"\xef\xc4\x9e\xc1\x93\xc9%\x12J\x9a\x83|p\x82\xb0}\xaa=\xdb{K\x04')
    # transceiver.first_packet_time = 1742558905.5647175
    # stream.first_packet_time = 1742558905.5647175
    # transceiver.send(b'Hello')
    # transceiver.send('"Tыя гaды пpымyciлi нac змaлкy дзён пpывyчвaццa дa плyгa i кacы, дa пiлы i cякepы, дa гэбля i дoлaтa, дa мoлaтa i кaвaдлa. Гэтae нaчыннe i пpылaддзe, пa якiм яшчэ нядaўнa xaдзiлi бaцькaвы pyкi, былo яшчэ i цяжкoe i вялiкae кoжнaмy з нac..." – зaзнaчae нa пaчaткy paмaнa aўтap.    Boлoчкa Hявaдa вяpтaeццa з кaнём з пoля. Aд бaцькi з фpoнтy ўжo бoльш зa пaўгoдa нямa пiceм. Дзяўчынкa caмa ўзapaлa пoлe. Kaля вёcкi янa cycтpэлa фypмaнкy, нa якoй cтaялa зaчынeнaя тpyнa, a пoбaч cядзeў "yвecь cцicнyты, cкaмeчaны пaлoнны". Гacпaдap фypмaнкi, xлoпeц-пaдлeтaк, пaxaвaў нa мoгiлкax cвaйгo бaцькy, якi нe вытpымaў дapoг бeжaнcтвa.'.encode('utf-8'))
    # return

    while True:
        try:
            transceiver.connect(True)
        except ConnectionAbortedError:
            LOGGER.info('Connection aborted, trying to reconnect...')


def receiver() -> None:
    if '--disable-log' in sys.argv:
        GGWave.disable_log()
        LOGGER.log_tags = ['I', 'W', 'E1']
        LOGGER.traceback_tags = LOGGER.LOG_NOTHING

    LOGGER.add_global_prefix('Receiver')
    stream: AlternativeStream = AlternativeStream(False)
    transceiver: ReliableTransceiver = ReliableTransceiver(stream)
    # transceiver.session_key = SymmetricKey(b'tUH\x19\x9d\x8bZK\xd0"\xef\xc4\x9e\xc1\x93\xc9%\x12J\x9a\x83|p\x82\xb0}\xaa=\xdb{K\x04')
    # transceiver.first_packet_time = 1742558905.5647175
    # stream.first_packet_time = 1742558905.5647175
    # LOGGER.info(transceiver.receive().decode())
    # return

    while True:
        try:
            transceiver.connect(False)
        except ConnectionAbortedError:
            LOGGER.info('Connection aborted, trying to reconnect...')

