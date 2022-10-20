import time
from enum import Enum

from alab_control._base_arduino_device import BaseArduinoDevice


class CapDispenserState(Enum):
    RUNNING = "RUNNING"
    STOPPED = "STOPPED"


class CapDispenser(BaseArduinoDevice):
    ENDPOINTS = {
        "state": "/state",
    }
    """
    Endpoints are:
    /state
    /open%20n=1
    /open%20n=2
    /open%20n=3
    /open%20n=4
    /close%20n=1
    /close%20n=2
    /close%20n=3
    /close%20n=4
    """

    def __init__(self, ip_address: str, port: int = 80):
        super().__init__(ip_address, port)
        self.is_open = [False] * 4

    def get_state(self) -> CapDispenserState:
        """
        Get the current state of the cap dispenser
        """
        return CapDispenserState[self.send_request(self.ENDPOINTS["state"], method="GET")["state"].upper()]

    def open(self, n: int):
        """
        Open the cap dispenser
        """
        if not 1 <= n <= 4:
            raise ValueError("n must be between 1 and 4")
        if self.get_state() == CapDispenserState.RUNNING:
            raise RuntimeError("Cannot open the cap dispenser while it is running")
        if self.is_open[n - 1]:
            raise RuntimeError("Cannot open the cap dispenser while it is open")
        command = f"/open%20n={n}"
        self.send_request(command, method="GET")
        while self.get_state() == CapDispenserState.RUNNING:
            time.sleep(1)

        self.is_open[n - 1] = True

    def close(self, n: int):
        """
        Close the cap dispenser
        """
        if not 1 <= n <= 4:
            raise ValueError("n must be between 1 and 4")
        if self.get_state() == CapDispenserState.RUNNING:
            raise RuntimeError("Cannot open the cap dispenser while it is running")
        if not self.is_open[n - 1]:
            raise RuntimeError("Cannot close the cap dispenser while it is closed")
        command = f"/close%20n={n}"
        self.send_request(command, method="GET")
        while self.get_state() == CapDispenserState.RUNNING:
            time.sleep(1)

        self.is_open[n - 1] = False
