"""Conservative Modbus RTU decoder; wire addresses are zero-based."""

from dataclasses import dataclass, field
import math


FUNCTIONS = {
    1: "Read coils", 2: "Read discrete inputs", 3: "Read holding registers",
    4: "Read input registers", 5: "Write single coil", 6: "Write single register",
    15: "Write multiple coils", 16: "Write multiple registers",
}
EXCEPTIONS = {
    1: "Illegal function", 2: "Illegal data address", 3: "Illegal data value",
    4: "Server device failure", 5: "Acknowledge", 6: "Server device busy",
    8: "Memory parity error", 10: "Gateway path unavailable",
    11: "Gateway target device failed to respond",
}


def crc16(data: bytes) -> int:
    crc = 0xFFFF
    for byte in data:
        crc ^= byte
        for _ in range(8):
            crc = (crc >> 1) ^ (0xA001 if crc & 1 else 0)
    return crc


def with_crc(payload: bytes) -> bytes:
    return payload + crc16(payload).to_bytes(2, "little")


def decode_frame(raw: bytes) -> dict:
    result = {
        "hex": raw.hex(" ").upper(), "length": len(raw), "address": None,
        "function": None, "function_name": "Unknown", "crc_valid": None,
        "role": "unknown", "candidates": [], "issues": [],
    }
    issues = result["issues"]
    if len(raw) < 4:
        issues.append("Frame too short: address, function and CRC are required")
        return result
    result["address"], result["function"] = raw[:2]
    result["crc_valid"] = crc16(raw[:-2]) == int.from_bytes(raw[-2:], "little")
    if not result["crc_valid"]:
        issues.append("CRC mismatch")
    if len(raw) > 256:
        issues.append("Frame exceeds the 256-byte RTU maximum")
    if raw[0] > 247:
        issues.append("Reserved serial address (248-255)")
    fn = raw[1]
    result["function_name"] = FUNCTIONS.get(fn & 0x7F, "Unsupported function")
    data = raw[2:-2]
    candidates = result["candidates"]
    if fn & 0x80:
        if len(data) == 1:
            candidates.append({"role": "response", "exception_code": data[0],
                               "exception_name": EXCEPTIONS.get(data[0], "Unknown exception")})
            if data[0] not in EXCEPTIONS:
                issues.append("Unrecognized exception code")
        else:
            issues.append("Exception response must contain one exception byte")
    elif fn in (1, 2, 3, 4):
        if len(data) == 4:
            start = int.from_bytes(data[:2], "big")
            count = int.from_bytes(data[2:], "big")
            limit = 2000 if fn in (1, 2) else 125
            if 1 <= count <= limit and start + count <= 65536:
                candidates.append({"role": "request", "start_address": start,
                                   "quantity": count})
        if data and data[0] == len(data) - 1:
            count = data[0]
            max_bytes = 250
            if 1 <= count <= max_bytes and (fn in (1, 2) or count % 2 == 0):
                response = {"role": "response", "byte_count": count}
                if fn in (3, 4):
                    response["registers"] = [int.from_bytes(data[i:i + 2], "big")
                                             for i in range(1, len(data), 2)]
                else:
                    # Quantity is only known when matched to a request. Padding remains raw.
                    response["packed_bits_hex"] = data[1:].hex(" ").upper()
                candidates.append(response)
    elif fn in (5, 6):
        # A supported function with the wrong length must not be reported as unsupported.
        if len(data) == 4:
            value = int.from_bytes(data[2:], "big")
            if fn == 6 or value in (0, 0xFF00):
                details = {"register_address": int.from_bytes(data[:2], "big"), "value": value}
                candidates.extend([{"role": role, **details} for role in ("request", "response")])
    elif fn in (15, 16):
        if len(data) >= 4:
            start, count = int.from_bytes(data[:2], "big"), int.from_bytes(data[2:4], "big")
            limit = 1968 if fn == 15 else 123
            if 1 <= count <= limit and start + count <= 65536:
                details = {"start_address": start, "quantity": count}
                if len(data) == 4:
                    candidates.append({"role": "response", **details})
                expected = (count + 7) // 8 if fn == 15 else count * 2
                if len(data) == 5 + expected and data[4] == expected:
                    candidates.append({"role": "request", **details,
                                       "values_hex": data[5:].hex(" ").upper()})
    else:
        issues.append("Function decoding is not supported; raw bytes retained")
    if fn in FUNCTIONS and not candidates:
        issues.append("Invalid length or values for this function")
    if raw[0] == 0:
        if fn in (1, 2, 3, 4):
            issues.append("Broadcast read is not a supported serial transaction")
        candidates[:] = [c for c in candidates if c["role"] == "request"]
        if not candidates:
            issues.append("Broadcast address cannot identify a response")
    roles = {c["role"] for c in candidates}
    # A bad CRC/address/structure cannot reliably identify the frame's direction.
    if not issues and roles:
        result["role"] = next(iter(roles)) if len(roles) == 1 else "ambiguous"
    return result


@dataclass(frozen=True)
class SerialTiming:
    baud: int = 9600
    parity: str = "E"
    stop_bits: int = 1

    def __post_init__(self):
        if isinstance(self.baud, bool) or not isinstance(self.baud, int) or self.baud <= 0:
            raise ValueError("Baud must be a positive integer")
        if self.parity not in ("N", "E", "O") or self.stop_bits not in (1, 2):
            raise ValueError("Use parity N/E/O and 1 or 2 stop bits")
        if self.parity == "N" and self.stop_bits != 2:
            raise ValueError("Modbus RTU without parity requires 2 stop bits")

    @property
    def character_us(self):
        return (1 + 8 + (self.parity != "N") + self.stop_bits) * 1_000_000 / self.baud

    @property
    def t1_5_us(self):
        return 750.0 if self.baud > 19200 else 1.5 * self.character_us

    @property
    def t3_5_us(self):
        return 1750.0 if self.baud > 19200 else 3.5 * self.character_us


@dataclass
class RtuFramer:
    """Frame device-timestamped bytes. Timestamps identify each byte's END.

    Host USB read times are unsuitable: batching can hide real wire gaps.
    Finish retains the last frame, whose trailing silence has not been verified.
    """

    timing: SerialTiming = field(default_factory=SerialTiming)
    _buffer: bytearray = field(default_factory=bytearray)
    _first: float | None = None
    _last: float | None = None
    _issues: list = field(default_factory=list)

    def _emit(self, trailing_verified=False):
        if not self._buffer:
            return None
        result = {
            "start_us": max(0.0, self._first - self.timing.character_us),
            "end_us": self._last, "hex": self._buffer.hex(" ").upper(),
            "timing_issues": list(self._issues),
            "trailing_silence_verified": trailing_verified,
        }
        self._buffer.clear()
        self._issues.clear()
        self._first = self._last = None
        return result

    def feed(self, byte: int, end_us: float):
        if isinstance(byte, bool) or not isinstance(byte, int) or not 0 <= byte <= 255:
            raise ValueError("Byte must be an integer from 0 to 255")
        if isinstance(end_us, bool) or not isinstance(end_us, (float, int)):
            raise ValueError("Byte-end timestamp must be numeric")
        if not math.isfinite(end_us) or end_us < 0:
            raise ValueError("Byte-end timestamp must be finite and nonnegative")
        frame = None
        if self._last is not None:
            elapsed = end_us - self._last
            if elapsed < self.timing.character_us - 0.01:
                raise ValueError("Byte-end timestamps overlap or are out of order")
            silence = elapsed - self.timing.character_us
            if silence >= self.timing.t3_5_us - 0.01:
                frame = self._emit(trailing_verified=True)
            elif silence > self.timing.t1_5_us + 0.01:
                if "Inter-character silence exceeds t1.5" not in self._issues:
                    self._issues.append("Inter-character silence exceeds t1.5")
        if len(self._buffer) >= 4096:
            raise ValueError("Unframed input exceeds 4096 bytes; check baud and timestamps")
        if not self._buffer:
            self._first = end_us
        self._buffer.append(byte)
        self._last = end_us
        return frame

    def finish(self):
        return self._emit()
