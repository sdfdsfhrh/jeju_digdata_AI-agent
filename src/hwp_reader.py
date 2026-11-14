"""
HWP 5.x 문서 읽기 (파이썬 표준 라이브러리만 사용)

HWP 5.x 파일 구조
- 파일 전체는 MS "OLE 복합 문서(Compound File)" 형식이다.
- 그 안의 "BodyText/Section0, Section1 ..." 스트림에 본문이 들어 있다.
- 본문 스트림은 보통 raw deflate로 압축되어 있고, 풀면 "레코드"가 줄지어 있다.
- 레코드 중 PARA_TEXT(문단 글자), LIST_HEADER(표 셀 시작), TABLE(표 시작)을 이용해
  본문 문단과 표의 셀(행·열 위치 포함)을 순서대로 뽑아낸다.

참고: 한글과컴퓨터 "한글 문서 파일 형식 5.0" 공개 문서
olefile 라이브러리가 설치되어 있으면 그것을 쓰고, 없으면 아래 자체 OLE 리더를 쓴다.
"""
from __future__ import annotations

import struct
import zlib
from dataclasses import dataclass, field

# ---------------------------------------------------------------------------
# 1. OLE 복합 문서 리더 (최소 구현)
# ---------------------------------------------------------------------------
ENDOFCHAIN = 0xFFFFFFFE
FREESECT = 0xFFFFFFFF


class MiniOle:
    """OLE 복합 문서에서 스트림을 이름으로 읽는 최소 구현."""

    def __init__(self, path: str):
        with open(path, "rb") as f:
            self.data = f.read()
        d = self.data
        if d[:8] != b"\xD0\xCF\x11\xE0\xA1\xB1\x1A\xE1":
            raise ValueError("OLE 복합 문서가 아님 (HWP 5.x가 아니거나 손상된 파일)")
        self.sector_size = 1 << struct.unpack_from("<H", d, 0x1E)[0]
        self.mini_sector_size = 1 << struct.unpack_from("<H", d, 0x20)[0]
        num_fat = struct.unpack_from("<I", d, 0x2C)[0]
        self.first_dir = struct.unpack_from("<I", d, 0x30)[0]
        self.mini_cutoff = struct.unpack_from("<I", d, 0x38)[0]
        first_minifat = struct.unpack_from("<I", d, 0x3C)[0]
        first_difat = struct.unpack_from("<I", d, 0x44)[0]
        num_difat = struct.unpack_from("<I", d, 0x48)[0]

        # DIFAT → FAT 섹터 목록
        difat = list(struct.unpack_from("<109I", d, 0x4C))
        sec = first_difat
        for _ in range(num_difat):
            if sec in (ENDOFCHAIN, FREESECT):
                break
            ints = struct.unpack_from(f"<{self.sector_size // 4}I", d, self._off(sec))
            difat.extend(ints[:-1])
            sec = ints[-1]
        fat_sectors = [s for s in difat if s not in (FREESECT, ENDOFCHAIN)][:num_fat]
        self.fat = []
        for s in fat_sectors:
            self.fat.extend(struct.unpack_from(f"<{self.sector_size // 4}I", d, self._off(s)))

        # 디렉터리
        dir_bytes = self._read_chain(self.first_dir)
        self.entries = []
        for i in range(len(dir_bytes) // 128):
            e = dir_bytes[i * 128:(i + 1) * 128]
            name_len = struct.unpack_from("<H", e, 0x40)[0]
            name = e[:max(name_len - 2, 0)].decode("utf-16-le", errors="ignore")
            etype = e[0x42]
            left, right, child = struct.unpack_from("<III", e, 0x44)
            start = struct.unpack_from("<I", e, 0x74)[0]
            size = struct.unpack_from("<Q", e, 0x78)[0]
            if self.sector_size == 512:
                size &= 0xFFFFFFFF
            self.entries.append(dict(name=name, type=etype, left=left, right=right,
                                     child=child, start=start, size=size))

        # 미니 스트림
        root = self.entries[0]
        self.mini_stream = self._read_chain(root["start"])[:root["size"]] if root["size"] else b""
        self.minifat = []
        if first_minifat not in (ENDOFCHAIN, FREESECT):
            mf = self._read_chain(first_minifat)
            self.minifat = list(struct.unpack_from(f"<{len(mf) // 4}I", mf))

        # 경로 → 엔트리 인덱스
        self.paths = {}
        self._walk(root["child"], "")

    def _off(self, sec: int) -> int:
        return (sec + 1) * self.sector_size

    def _read_chain(self, start: int) -> bytes:
        out, sec, seen = [], start, set()
        while sec not in (ENDOFCHAIN, FREESECT) and sec < len(self.fat) and sec not in seen:
            seen.add(sec)
            o = self._off(sec)
            out.append(self.data[o:o + self.sector_size])
            sec = self.fat[sec]
        return b"".join(out)

    def _read_mini_chain(self, start: int) -> bytes:
        out, sec, seen = [], start, set()
        ms = self.mini_sector_size
        while sec not in (ENDOFCHAIN, FREESECT) and sec < len(self.minifat) and sec not in seen:
            seen.add(sec)
            out.append(self.mini_stream[sec * ms:(sec + 1) * ms])
            sec = self.minifat[sec]
        return b"".join(out)

    def _walk(self, idx: int, prefix: str):
        stack = [(idx, prefix)]
        while stack:
            i, pre = stack.pop()
            if i == FREESECT or i >= len(self.entries):
                continue
            e = self.entries[i]
            path = f"{pre}/{e['name']}" if pre else e["name"]
            self.paths[path] = i
            stack.append((e["left"], pre))
            stack.append((e["right"], pre))
            if e["type"] == 1:  # storage(폴더)
                stack.append((e["child"], path))

    def listdir(self):
        return sorted(self.paths)

    def exists(self, path: str) -> bool:
        return path in self.paths

    def read(self, path: str) -> bytes:
        e = self.entries[self.paths[path]]
        if e["size"] < self.mini_cutoff:
            return self._read_mini_chain(e["start"])[:e["size"]]
        return self._read_chain(e["start"])[:e["size"]]


def open_ole(path: str):
    """olefile이 있으면 사용, 없으면 자체 리더 사용. (read, exists, listdir) 인터페이스 통일."""
    try:
        import olefile  # type: ignore

        ole = olefile.OleFileIO(path)

        class _Wrap:
            def close(self):
                ole.close()

            def read(self, p):
                return ole.openstream(p).read()

            def exists(self, p):
                return ole.exists(p)

            def listdir(self):
                return ["/".join(x) for x in ole.listdir()]

        return _Wrap(), "olefile"
    except ImportError:
        return MiniOle(path), "builtin"


# ---------------------------------------------------------------------------
# 2. HWP 레코드 파싱
# ---------------------------------------------------------------------------
HWPTAG_BEGIN = 0x10
TAG_PARA_HEADER = HWPTAG_BEGIN + 50
TAG_PARA_TEXT = HWPTAG_BEGIN + 51
TAG_CTRL_HEADER = HWPTAG_BEGIN + 55
TAG_LIST_HEADER = HWPTAG_BEGIN + 56
TAG_TABLE = HWPTAG_BEGIN + 61

# 8 WCHAR(16바이트)를 차지하는 제어 문자 (인라인·확장 컨트롤)
WIDE_CTRL = {1, 2, 3, 4, 5, 6, 7, 8, 9, 11, 12, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23}


def iter_records(buf: bytes):
    pos = 0
    n = len(buf)
    while pos + 4 <= n:
        h = struct.unpack_from("<I", buf, pos)[0]
        pos += 4
        tag, level, size = h & 0x3FF, (h >> 10) & 0x3FF, (h >> 20) & 0xFFF
        if size == 0xFFF:
            size = struct.unpack_from("<I", buf, pos)[0]
            pos += 4
        yield tag, level, buf[pos:pos + size]
        pos += size


def decode_para_text(payload: bytes) -> str:
    out = []
    i, n = 0, len(payload) // 2
    while i < n:
        c = struct.unpack_from("<H", payload, i * 2)[0]
        if c < 32:
            if c in WIDE_CTRL:
                i += 8
                continue
            if c in (10, 13):
                out.append("\n")
            elif c == 9:
                out.append("\t")
            i += 1
            continue
        out.append(chr(c))
        i += 1
    return "".join(out)


@dataclass
class Block:
    """본문 문단 또는 표 셀 하나."""
    kind: str                 # "para" 또는 "cell"
    text: str
    table_no: int | None = None
    row: int | None = None
    col: int | None = None
    order: int = 0


@dataclass
class HwpDoc:
    path: str
    reader: str
    compressed: bool
    blocks: list = field(default_factory=list)

    def tables(self):
        """표 번호별로 {(row, col): text} 딕셔너리 반환."""
        out = {}
        for b in self.blocks:
            if b.kind == "cell":
                out.setdefault(b.table_no, {})[(b.row, b.col)] = b.text
        return out

    def plain_text(self) -> str:
        return "\n".join(b.text for b in self.blocks if b.text.strip())


def read_hwp(path: str) -> HwpDoc:
    ole, reader = open_ole(path)
    try:
        return _read_hwp_contents(path,ole,reader)
    finally:
        close=getattr(ole,"close",None)
        if close: close()


def _read_hwp_contents(path,ole,reader):
    header = ole.read("FileHeader")
    if not header.startswith(b"HWP Document File"):
        raise ValueError("HWP 파일 헤더가 아님")
    flags = struct.unpack_from("<I", header, 36)[0]
    compressed, encrypted = bool(flags & 1), bool(flags & 2)
    if encrypted:
        raise ValueError("암호가 걸린 HWP 파일")

    doc = HwpDoc(path=path, reader=reader, compressed=compressed)
    sections = sorted(
        (p for p in ole.listdir() if p.startswith("BodyText/Section")),
        key=lambda p: int(p.rsplit("Section", 1)[1]),
    )
    if not sections:
        raise ValueError("BodyText 섹션이 없음 (배포용 문서이거나 손상)")

    order = 0
    table_no = -1
    for sec in sections:
        raw = ole.read(sec)
        buf = zlib.decompress(raw, -15) if compressed else raw

        # 표/셀 위치 추적용 스택: (표 레벨, 표 번호)
        table_stack = []
        cur_cell = None      # (table_no, row, col, cell_level)
        cell_texts = []

        def flush_cell():
            nonlocal cur_cell, cell_texts, order
            if cur_cell is not None:
                t = "\n".join(x for x in cell_texts).strip()
                doc.blocks.append(Block("cell", t, cur_cell[0], cur_cell[1], cur_cell[2], order))
                order += 1
            cur_cell, cell_texts = None, []

        for tag, level, data in iter_records(buf):
            # 표가 끝났는지 확인 (현재 레코드 레벨이 표 레벨 이하로 내려오면 종료)
            while table_stack and level <= table_stack[-1][0] and tag != TAG_TABLE:
                flush_cell()
                table_stack.pop()

            if tag == TAG_CTRL_HEADER and data[:4] == b" lbt":  # 'tbl '을 리틀엔디언으로 저장
                table_no += 1
                table_stack.append((level, table_no))
                continue

            if tag == TAG_LIST_HEADER and table_stack and level == table_stack[-1][0] + 1:
                # 표 셀 시작: 리스트 헤더(8바이트) 다음에 열·행 주소
                flush_cell()
                col, row = struct.unpack_from("<HH", data, 8) if len(data) >= 12 else (None, None)
                cur_cell = (table_stack[-1][1], row, col, level)
                continue

            if tag == TAG_PARA_TEXT:
                text = decode_para_text(data).strip("\n")
                if cur_cell is not None and level > cur_cell[3]:
                    cell_texts.append(text)
                else:
                    doc.blocks.append(Block("para", text, order=order))
                    order += 1
        flush_cell()
    return doc


if __name__ == "__main__":
    import sys

    d = read_hwp(sys.argv[1])
    print(f"reader={d.reader} compressed={d.compressed} blocks={len(d.blocks)}")
    for b in d.blocks[:200]:
        loc = f"T{b.table_no} r{b.row} c{b.col}" if b.kind == "cell" else "P"
        print(f"[{loc}] {b.text[:100]!r}")
