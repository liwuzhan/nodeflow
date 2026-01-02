from typing import Optional, Dict, Any

class LatestValueReader:
    def __init__(self, sock):
        self.sock = sock

    def read_latest(self) -> Optional[Dict[str, Any]]:
        return None

    def read_latest_blocking(self, timeout: Optional[float] = None) -> Optional[Dict[str, Any]]:
        return None
