from PySide6 import QtCore, QtWidgets, QtGui

import sys

from gui_theme import qInitResources, qCleanupResources


class MessengerWindow(QtWidgets.QWidget):
    def __init__(self) -> None:
        super().__init__()

        self.text_loading = QtWidgets.QLabel("Select mode to work in", alignment=QtCore.Qt.AlignCenter)
        self.button_sender = QtWidgets.QPushButton("Sender")
        self.button_receiver = QtWidgets.QPushButton("Receiver")

        self.layout = QtWidgets.QVBoxLayout(self)
        self.layout.addWidget(self.text_loading)
        self.layout.addWidget(self.button_sender)
        self.layout.addWidget(self.button_receiver)

        self.button_sender.clicked.connect(self._on_sender_button_pressed)
        self.button_receiver.clicked.connect(self._on_receiver_button_pressed)

    @QtCore.Slot()
    def _on_sender_button_pressed(self) -> None:
        print('Sender selected')

    @QtCore.Slot()
    def _on_receiver_button_pressed(self) -> None:
        print('Receiver selected')

def show() -> None:
    qInitResources()
    app = QtWidgets.QApplication(sys.argv)

    window = MessengerWindow()
    window.resize(800, 600)
    window.show()

    exitcode: int = app.exec()
    qCleanupResources()
    sys.exit(exitcode)

