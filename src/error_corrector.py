"""
Frame ends with `FREQ_1 | FREQ_TRANSMIT`. After sending it fully, sender
waits 1.5-2 seconds and then:
- if other peer sent `FREQ_2 | FREQ_TRANSMIT` then it is success;
- if other peer sent `FREQ_3 | FREQ_TRANSMIT` then it is a failure, so resend
the entire frame;
- if no response was received, resend `FREQ_1 | FREQ_TRANSMIT`, wait 1.5-2
seconds for response again, resend it again and if after 1.5-2 seconds there
is still no response, consider session invalid, reset everything and prepare
to connect to other peer.
"""

from collections.abc import Generator
import reedsolo  # type: ignore

EC_BLOCK_SIZE = 16
REDUNDANCY_SIZE = 6


class ErrorCorrector:
    """
    Data to be error-corrected. Can encode/decode.
    """

    data: bytes
    rscodec: reedsolo.RSCodec

    def __init__(self, data: bytes):
        self.data = data
        self.rscodec = reedsolo.RSCodec(
            REDUNDANCY_SIZE,
            EC_BLOCK_SIZE + REDUNDANCY_SIZE,
        )

    def encode(self) -> bytes:
        # Encode the data (adds redundancy)
        encoded_data = self.rscodec.encode(self.data)
        return bytes(encoded_data)

    def decode(self) -> bytes:
        try:
            # Decode the data (corrects errors using redundancy)
            decoded_data, _, _ = self.rscodec.decode(self.data)
            return bytes(decoded_data)
        except reedsolo.ReedSolomonError as e:
            # If too many errors to correct
            raise ValueError(f"Unable to decode: {str(e)}") from e

    @staticmethod
    def break_into_frames(packet: bytes) -> Generator[bytes]:
        while packet:
            yield packet[:EC_BLOCK_SIZE - REDUNDANCY_SIZE]
            packet = packet[EC_BLOCK_SIZE - REDUNDANCY_SIZE:]
