from typing import Any
from npyscreen import ButtonPress, FixedText, Form, MultiLineEdit, NPSApp
import npyscreen
import pyggwave

from log import LOGGER


class UIProcessor(NPSApp):
    transceiver: Any

    def __init__(self, transceiver: Any) -> None:
        super().__init__()

        self.transceiver = transceiver

        LOGGER.log_stdout_tags.clear()
        LOGGER.log_stderr_tags.clear()
        pyggwave.GGWave.disable_log()

    def main(self) -> None:
        self.form = Form(name="SoundCommunication")
        self.status_label = self.form.add(FixedText, value='Status: idle', editable=False)
        self.message_input = self.form.add(MultiLineEdit, name='Message:', max_height=40)
        self.send_text_button = self.form.add(ButtonPress, name='Send text', when_pressed_function=self._on_send_text_button_pressed)
        self.send_file_button = self.form.add(ButtonPress, name='Send file', when_pressed_function=self._on_send_file_button_pressed)
        self.receive_button = self.form.add(ButtonPress, name='Receive data', when_pressed_function=self._on_receive_button_pressed)
        self.form.edit()

    def send(self, data: bytes) -> None:
        self.transceiver.send(data)

    def receive(self) -> bytes:
        return self.transceiver.receive()

    def _on_send_text_button_pressed(self) -> None:
        self.status_label.value = f'Sending message'
        self.form.display()
        self.send(self.message_input.value.encode())
        self.status_label.value = f'Idle (text sent)'

    def _on_send_file_button_pressed(self) -> None:
        path = npyscreen.selectFile(must_exist=True, confirm_if_exists=False)
        self.status_label.value = f'Sending file: "{path}"'
        self.form.display()

        with open(path, 'rb') as file:
            self.send(file.read())

        self.status_label.value = f'Idle (file sent)'
        self.form.display()

    def _on_receive_button_pressed(self) -> bytes:
        self.status_label.value = 'Receiving input...'
        self.form.display()

        data: bytes = self.receive()

        try:
            self.message_input.value = data.decode()
            self.status_label.value = f'Idle (text received)'
        except UnicodeError:
            self.message_input.value = data.hex()
            self.status_label.value = f'Idle (binary received)'

        self.form.display()

