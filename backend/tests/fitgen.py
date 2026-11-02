"""Tiny FIT writer for tests (record + session messages)."""

import io
import struct
import zipfile

FIT_EPOCH = 631065600
_TABLE = [0x0000, 0xCC01, 0xD801, 0x1400, 0xF001, 0x3C00, 0x2800, 0xE401,
          0xA001, 0x6C00, 0x7800, 0xB401, 0x5000, 0x9C01, 0x8801, 0x4400]


def crc16(data: bytes, crc: int = 0) -> int:
    for b in data:
        tmp = _TABLE[crc & 0xF]
        crc = (crc >> 4) & 0x0FFF
        crc = crc ^ tmp ^ _TABLE[b & 0xF]
        tmp = _TABLE[crc & 0xF]
        crc = (crc >> 4) & 0x0FFF
        crc = crc ^ tmp ^ _TABLE[(b >> 4) & 0xF]
    return crc


UINT8, SINT32, UINT16, UINT32, ENUM = 0x02, 0x85, 0x84, 0x86, 0x00
_SIZE = {UINT8: 1, ENUM: 1, SINT32: 4, UINT16: 2, UINT32: 4}
_FMT = {UINT8: "<B", ENUM: "<B", SINT32: "<i", UINT16: "<H", UINT32: "<I"}


def _definition(local: int, global_num: int, fields: list[tuple[int, int]]) -> bytes:
    out = struct.pack("<BBBHB", 0x40 | local, 0, 0, global_num, len(fields))
    for num, base in fields:
        out += struct.pack("<BBB", num, _SIZE[base], base)
    return out


def _data(local: int, fields: list[tuple[int, int]], values: list[int]) -> bytes:
    out = bytes([local])
    for (_, base), v in zip(fields, values):
        out += struct.pack(_FMT[base], v)
    return out


RECORD = [(253, UINT32), (0, SINT32), (1, SINT32), (5, UINT32), (2, UINT16), (6, UINT16),
          (3, UINT8), (4, UINT8)]
SESSION = [(253, UINT32), (2, UINT32), (7, UINT32), (8, UINT32), (9, UINT32), (5, ENUM),
           (22, UINT16), (16, UINT8), (17, UINT8)]


# lap message (global 19): timestamp, start_time, total_elapsed_time, total_timer_time, total_distance, avg_speed (scale 1000),
# avg_heart_rate, max_heart_rate, avg_cadence, avg_power, total_ascent, total_descent, intensity, lap_trigger, message_index
LAP = [(253, UINT32), (2, UINT32), (7, UINT32), (8, UINT32), (9, UINT32), (13, UINT16), (15, UINT8), (16, UINT8), (17, UINT8),
       (19, UINT16), (21, UINT16), (22, UINT16), (23, ENUM), (24, ENUM), (254, UINT16)]


def semicircles(deg: float) -> int:
    return int(deg * 2**31 / 180)


def make_fit(start_unix: int = 1_760_000_000, n: int = 5, sport: int = 1, laps: list[dict] | None = None) -> bytes:
    body = _definition(0, 20, RECORD)
    for i in range(n):
        body += _data(0, RECORD, [
            start_unix - FIT_EPOCH + i,
            semicircles(49.28 + i * 0.0001), semicircles(-123.12 + i * 0.0001),
            i * 300,                       # distance, scale 100 -> metres
            (100 + i) * 5 + 2500,          # altitude, scale 5 offset 500
            3000 + i * 10,                 # speed, scale 1000 -> m/s
            140 + i, 85,
        ])
    if laps:
        body += _definition(2, 19, LAP)
        t = start_unix - FIT_EPOCH
        for i, lap in enumerate(laps):
            secs = lap["secs"]
            body += _data(2, LAP, [t + secs, t, secs * 1000, secs * 1000, int(lap["dist"] * 100),
                                   int(lap["dist"] / secs * 1000), lap.get("hr", 150), lap.get("hrmax", 160), lap.get("cad", 85),
                                   lap.get("power", 0), lap.get("up", 5), lap.get("down", 3), lap.get("intensity", 0),
                                   lap.get("trigger", 2), i])
            t += secs
    body += _definition(1, 18, SESSION)
    body += _data(1, SESSION, [
        start_unix - FIT_EPOCH + n, start_unix - FIT_EPOCH, n * 1000, n * 1000,
        (n - 1) * 300 * 100, sport, 12, 142, 144,
    ])
    header = struct.pack("<BBHI4s", 14, 0x20, 2000, len(body), b".FIT")
    header += struct.pack("<H", crc16(header))
    return header + body + struct.pack("<H", crc16(header + body))


def make_zip(fit: bytes, name: str = "activity.fit") -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr(name, fit)
    return buf.getvalue()
