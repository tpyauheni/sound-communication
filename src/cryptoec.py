import monocypher
import struct


# `PublicKey` and `SecretKey` are separate to make sure one won't be passed as another.
class PublicKey:
    __pkey: bytes

    def __init__(self, key: bytes) -> None:
        self.__pkey = key

    def pubkey(self) -> bytes:
        return self.__pkey

    def seckey(self) -> bytes:
        raise NotImplementedError('Tried to access secret key from a public key')


# This class must not be used outside of that module!
class SecretKey:
    __skey: bytes

    def __init__(self, key: bytes) -> None:
        self.__skey = key

    def pubkey(self) -> bytes:
        # With an exclamation mark because it's scary.
        raise NotImplementedError('Tried to access public key from a secret key!')

    def seckey(self) -> bytes:
        return self.__skey


# Must only be used in one thread!
class SymmetricKey:
    # List is used here to pass that object by reference
    # so it can be securely wiped after its use.
    __symkey: list[bytes] | None
    _nonce_counter: int

    def __init__(self, key: bytes) -> None:
        self.__symkey = [key]
        self._nonce_counter = 0

    def next_nonce(self) -> bytes:
        nonce: bytes = struct.pack('<Q', self._nonce_counter)
        self._nonce_counter += 1
        self._nonce_counter %= 256**8
        return nonce

    def encrypt(self, data: bytes) -> bytes:
        assert self.__symkey
        nonce: bytes = self.next_nonce()
        return nonce + monocypher.chacha20(self.__symkey[0], nonce, data)

    def decrypt(self, data: bytes) -> bytes:
        assert self.__symkey
        nonce: bytes = data[:8]
        ciphertext: bytes = data[8:]
        return monocypher.chacha20(self.__symkey[0], nonce, ciphertext)

    def dispose(self) -> None:
        assert self.__symkey
        symkey: list[bytes] = self.__symkey
        self.__symkey = None
        monocypher.wipe(symkey[0])

    def key_ref(self) -> list[bytes]:
        assert self.__symkey
        return self.__symkey


# Must only be used in one thread!
class KeyExchanger:
    _public_key: PublicKey
    _secret_key: SecretKey | None = None

    @staticmethod
    def generate_key_pair() -> tuple[SecretKey, PublicKey]:
        key_pair: tuple[bytes, bytes] = monocypher.generate_key_exchange_key_pair()
        return (SecretKey(key_pair[0]), PublicKey(key_pair[1]))

    def __init__(self, secret_key: SecretKey | None, public_key: PublicKey | None) -> None:
        if [secret_key is None, public_key is None].count(True) == 1:
            raise ValueError('Both `secret_key` and `public_key` must either be `None` or valid objects')

        # `or` here is unnecessary but is used to suppress static analysis warnings
        if secret_key is None or public_key is None:
            secret_key, public_key = self.generate_key_pair()

        self._secret_key = secret_key
        self._public_key = public_key

    def exchange_pubkey(self) -> bytes:
        return self._public_key.pubkey()

    def _compute_secret(self, their_pubkey: bytes) -> bytes:
        assert self._secret_key
        return monocypher.key_exchange(self._secret_key.seckey(), their_pubkey)

    def get_symkey(self, their_pubkey: bytes, dispose: bool = True) -> SymmetricKey:
        key = SymmetricKey(self._compute_secret(their_pubkey))

        if dispose:
            self.dispose()

        return key

    def dispose(self):
        # Before calling `wipe` we must be sure that we have the only active reference
        assert self._secret_key
        secret_key: SecretKey = self._secret_key
        self._secret_key = None
        monocypher.wipe(secret_key.seckey())

    def pubkey(self) -> bytes:
        return self._public_key.pubkey()

    def seckey(self) -> bytes:
        assert self._secret_key
        return self._secret_key.seckey()

