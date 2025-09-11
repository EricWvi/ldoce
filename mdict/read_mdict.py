#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Adapted from the original mdict-py project
import json
import re
import sys
import zlib
from enum import unique, StrEnum
from io import BytesIO
from struct import pack, unpack
from typing import Dict

from mdict.utils.pureSalsa20 import Salsa20
from mdict.utils.ripemd128 import ripemd128

try:
    from mdict.utils import lzo
except ImportError:
    lzo = None
    print("LZO compression support is not available")

if sys.hexversion >= 0x03000000:
    unicode = str


@unique
class NumberFmt(StrEnum):
    be_uint = ">I"
    be_ulonglong = ">Q"
    be_ushort = ">H"
    be_uchar = ">B"
    le_uint = "<I"
    le_ulonglong = "<Q"


def _unescape_entities(text):
    text = text.replace(b"&lt;", b"<")
    text = text.replace(b"&gt;", b">")
    text = text.replace(b"&quot;", b'"')
    text = text.replace(b"&amp;", b"&")
    return text


def _fast_decrypt(data, key):
    b = bytearray(data)
    key = bytearray(key)
    previous = 0x36
    for i in range(len(b)):
        t = (b[i] >> 4 | b[i] << 4) & 0xFF
        t = t ^ previous ^ (i & 0xFF) ^ key[i % len(key)]
        previous = b[i]
        b[i] = t
    return bytes(b)


def _mdx_decrypt(comp_block):
    key = ripemd128(comp_block[4:8] + pack(b"<L", 0x3695))
    return comp_block[0:8] + _fast_decrypt(comp_block[8:], key)


def _salsa_decrypt(ciphertext, encrypt_key):
    s20 = Salsa20(key=encrypt_key, IV=b"\x00" * 8, rounds=8)
    return s20.encryptBytes(ciphertext)


def _decrypt_regcode_by_deviceid(reg_code, deviceid):
    deviceid_digest = ripemd128(deviceid)
    s20 = Salsa20(key=deviceid_digest, IV=b"\x00" * 8, rounds=8)
    encrypt_key = s20.encryptBytes(reg_code)
    return encrypt_key


def _decrypt_regcode_by_email(reg_code, email):
    email_digest = ripemd128(email.decode().encode("utf-16-le"))
    s20 = Salsa20(key=email_digest, IV=b"\x00" * 8, rounds=8)
    encrypt_key = s20.encryptBytes(reg_code)
    return encrypt_key


def _parse_header(header) -> Dict[str, str]:
    tag_list = re.findall(b'(\\w+)="(.*?)"', header, re.DOTALL)
    tag_dict = {}
    for k, v in tag_list:
        tag_dict[k] = _unescape_entities(v)
    return tag_dict


class MDict(object):
    def __init__(self, fname, encoding="", passcode=None):
        self._fname = fname
        self._encoding = encoding.upper()
        self._passcode = passcode

        self.header = self._read_header()
        try:
            self._key_list = self._read_keys()
        except:
            print("Try Brutal Force on Encrypted Key Blocks")
            self._key_list = self._read_keys_brutal()

    def __len__(self):
        return self._num_entries

    def __iter__(self):
        return self.keys()

    def keys(self):
        return (key_value for key_id, key_value in self._key_list)

    def _read_number(self, f):
        return unpack(self._number_format, f.read(self._number_width))[0]

    def _decode_key_block_info(self, key_block_info_compressed):
        if self._version >= 2:
            assert key_block_info_compressed[:4] == b"\x02\x00\x00\x00"
            if self._encrypt & 0x02:
                key_block_info_compressed = _mdx_decrypt(key_block_info_compressed)
            key_block_info = zlib.decompress(key_block_info_compressed[8:])
            adler32 = unpack(NumberFmt.be_uint, key_block_info_compressed[4:8])[0]
            assert adler32 == zlib.adler32(key_block_info) & 0xFFFFFFFF
        else:
            key_block_info = key_block_info_compressed
        
        key_block_info_list = []
        num_entries = 0
        i = 0
        if self._version >= 2:
            byte_format = NumberFmt.be_ushort
            byte_width = 2
            text_term = 1
        else:
            byte_format = NumberFmt.be_uchar
            byte_width = 1
            text_term = 0

        while i < len(key_block_info):
            num_entries += unpack(
                self._number_format, key_block_info[i : i + self._number_width]
            )[0]
            i += self._number_width
            text_head_size = unpack(byte_format, key_block_info[i : i + byte_width])[0]
            i += byte_width
            if self._encoding != "UTF-16":
                i += text_head_size + text_term
            else:
                i += (text_head_size + text_term) * 2
            text_tail_size = unpack(byte_format, key_block_info[i : i + byte_width])[0]
            i += byte_width
            if self._encoding != "UTF-16":
                i += text_tail_size + text_term
            else:
                i += (text_tail_size + text_term) * 2
            key_block_compressed_size = unpack(
                self._number_format, key_block_info[i : i + self._number_width]
            )[0]
            i += self._number_width
            key_block_decompressed_size = unpack(
                self._number_format, key_block_info[i : i + self._number_width]
            )[0]
            i += self._number_width
            key_block_info_list += [
                (key_block_compressed_size, key_block_decompressed_size)
            ]

        assert num_entries == self._num_entries
        return key_block_info_list

    def _decode_key_block(self, key_block_compressed, key_block_info_list):
        key_list = []
        i = 0
        for compressed_size, decompressed_size in key_block_info_list:
            start = i
            end = i + compressed_size
            key_block_type = key_block_compressed[start : start + 4]
            adler32 = unpack(
                NumberFmt.be_uint, key_block_compressed[start + 4 : start + 8]
            )[0]
            if key_block_type == b"\x00\x00\x00\x00":
                key_block = key_block_compressed[start + 8 : end]
            elif key_block_type == b"\x01\x00\x00\x00":
                if lzo is None:
                    print("LZO compression is not supported")
                    break
                header = b"\xf0" + pack(NumberFmt.be_uint, decompressed_size)
                key_block = lzo.decompress(
                    key_block_compressed[start + 8 : end],
                    initSize=decompressed_size,
                    blockSize=1308672,
                )
            elif key_block_type == b"\x02\x00\x00\x00":
                key_block = zlib.decompress(key_block_compressed[start + 8 : end])
            
            key_list += self._split_key_block(key_block)
            assert adler32 == zlib.adler32(key_block) & 0xFFFFFFFF
            i += compressed_size
        return key_list

    def _split_key_block(self, key_block):
        key_list = []
        key_start_index = 0
        while key_start_index < len(key_block):
            key_id = unpack(
                self._number_format,
                key_block[key_start_index : key_start_index + self._number_width],
            )[0]
            if self._encoding == "UTF-16":
                delimiter = b"\x00\x00"
                width = 2
            else:
                delimiter = b"\x00"
                width = 1
            i = key_start_index + self._number_width
            while i < len(key_block):
                if key_block[i : i + width] == delimiter:
                    key_end_index = i
                    break
                i += width
            key_text = (
                key_block[key_start_index + self._number_width : key_end_index]
                .decode(self._encoding, errors="ignore")
                .encode("utf-8")
                .strip()
            )
            key_start_index = key_end_index + width
            key_list += [(key_id, key_text)]
        return key_list

    def _read_header(self):
        f = open(self._fname, "rb")
        header_bytes_size = unpack(NumberFmt.be_uint, f.read(4))[0]
        header_bytes = f.read(header_bytes_size)
        adler32 = unpack(NumberFmt.le_uint, f.read(4))[0]
        assert adler32 == zlib.adler32(header_bytes) & 0xFFFFFFFF
        self._key_block_offset = f.tell()
        f.close()

        header_text = header_bytes[:-2].decode("utf-16").encode("utf-8")
        header_tag = _parse_header(header_text)
        if not self._encoding:
            encoding = header_tag[b"Encoding"]
            if sys.hexversion >= 0x03000000:
                encoding = encoding.decode("utf-8")
            if encoding in ["GBK", "GB2312"]:
                encoding = "GB18030"
            self._encoding = encoding
        
        if b"Title" in header_tag:
            self._title = header_tag[b"Title"].decode("utf-8")
        else:
            self._title = ""

        if b"Description" in header_tag:
            self._description = header_tag[b"Description"].decode("utf-8")
        else:
            self._description = ""

        if b"Encrypted" not in header_tag or header_tag[b"Encrypted"] == b"No":
            self._encrypt = 0
        elif header_tag[b"Encrypted"] == b"Yes":
            self._encrypt = 1
        else:
            self._encrypt = int(header_tag[b"Encrypted"])

        self._stylesheet = {}
        if header_tag.get("StyleSheet"):
            lines = header_tag["StyleSheet"].splitlines()
            for i in range(0, len(lines), 3):
                self._stylesheet[lines[i]] = (lines[i + 1], lines[i + 2])

        self._version = float(header_tag[b"GeneratedByEngineVersion"])
        if self._version < 2.0:
            self._number_width = 4
            self._number_format = NumberFmt.be_uint
        else:
            self._number_width = 8
            self._number_format = NumberFmt.be_ulonglong

        return header_tag

    def _read_keys(self):
        f = open(self._fname, "rb")
        f.seek(self._key_block_offset)

        if self._version >= 2.0:
            num_bytes = 8 * 5
        else:
            num_bytes = 4 * 4
        block = f.read(num_bytes)

        if self._encrypt & 1:
            if self._passcode is None:
                raise RuntimeError(
                    "user identification is needed to read encrypted file"
                )
            regcode, userid = self._passcode
            if isinstance(userid, unicode):
                userid = userid.encode("utf8")
            if self.header[b"RegisterBy"] == b"EMail":
                encrypted_key = _decrypt_regcode_by_email(regcode, userid)
            else:
                encrypted_key = _decrypt_regcode_by_deviceid(regcode, userid)
            block = _salsa_decrypt(block, encrypted_key)

        sf = BytesIO(block)
        num_key_blocks = self._read_number(sf)
        self._num_entries = self._read_number(sf)
        if self._version >= 2.0:
            key_block_info_decomp_size = self._read_number(sf)
        key_block_info_size = self._read_number(sf)
        key_block_size = self._read_number(sf)

        if self._version >= 2.0:
            adler32 = unpack(NumberFmt.be_uint, f.read(4))[0]
            assert adler32 == (zlib.adler32(block) & 0xFFFFFFFF)

        key_block_info = f.read(key_block_info_size)
        key_block_info_list = self._decode_key_block_info(key_block_info)
        assert num_key_blocks == len(key_block_info_list)

        key_block_compressed = f.read(key_block_size)
        key_list = self._decode_key_block(key_block_compressed, key_block_info_list)

        self._record_block_offset = f.tell()
        f.close()

        return key_list

    def _read_keys_brutal(self):
        f = open(self._fname, "rb")
        f.seek(self._key_block_offset)

        if self._version >= 2.0:
            num_bytes = 8 * 5 + 4
            key_block_type = b"\x02\x00\x00\x00"
        else:
            num_bytes = 4 * 4
            key_block_type = b"\x01\x00\x00\x00"
        block = f.read(num_bytes)

        key_block_info = f.read(8)
        if self._version >= 2.0:
            assert key_block_info[:4] == b"\x02\x00\x00\x00"
        while True:
            fpos = f.tell()
            t = f.read(1024)
            index = t.find(key_block_type)
            if index != -1:
                key_block_info += t[:index]
                f.seek(fpos + index)
                break
            else:
                key_block_info += t

        key_block_info_list = self._decode_key_block_info(key_block_info)
        key_block_size = sum(list(zip(*key_block_info_list))[0])

        key_block_compressed = f.read(key_block_size)
        key_list = self._decode_key_block(key_block_compressed, key_block_info_list)

        self._record_block_offset = f.tell()
        f.close()

        self._num_entries = len(key_list)
        return key_list


class MDD(MDict):
    def __init__(self, fname, passcode=None):
        MDict.__init__(self, fname, encoding="UTF-16", passcode=passcode)

    def get_index(self, check_block=True):
        f = open(self._fname, "rb")
        index_dict_list = []
        f.seek(self._record_block_offset)

        num_record_blocks = self._read_number(f)
        num_entries = self._read_number(f)
        assert num_entries == self._num_entries
        record_block_info_size = self._read_number(f)
        record_block_size = self._read_number(f)

        record_block_info_list = []
        size_counter = 0
        for i in range(num_record_blocks):
            compressed_size = self._read_number(f)
            decompressed_size = self._read_number(f)
            record_block_info_list += [(compressed_size, decompressed_size)]
            size_counter += self._number_width * 2
        assert size_counter == record_block_info_size

        offset = 0
        i = 0
        size_counter = 0
        for compressed_size, decompressed_size in record_block_info_list:
            current_pos = f.tell()
            record_block_compressed = f.read(compressed_size)
            record_block_type = record_block_compressed[:4]
            adler32 = unpack(NumberFmt.be_uint, record_block_compressed[4:8])[0]
            
            if record_block_type == b"\x00\x00\x00\x00":
                _type = 0
                if check_block:
                    record_block = record_block_compressed[8:]
            elif record_block_type == b"\x01\x00\x00\x00":
                _type = 1
                if lzo is None:
                    print("LZO compression is not supported")
                    break
                if check_block:
                    record_block = lzo.decompress(
                        record_block_compressed[8:],
                        initSize=decompressed_size,
                        blockSize=1308672,
                    )
            elif record_block_type == b"\x02\x00\x00\x00":
                _type = 2
                if check_block:
                    record_block = zlib.decompress(record_block_compressed[8:])

            if check_block:
                assert adler32 == zlib.adler32(record_block) & 0xFFFFFFFF
                assert len(record_block) == decompressed_size
                
            while i < len(self._key_list):
                index_dict = {}
                index_dict["file_pos"] = current_pos
                index_dict["compressed_size"] = compressed_size
                index_dict["decompressed_size"] = decompressed_size
                index_dict["record_block_type"] = _type
                record_start, key_text = self._key_list[i]
                index_dict["record_start"] = record_start
                index_dict["key_text"] = key_text.decode("utf-8")
                index_dict["offset"] = offset
                
                if record_start - offset >= decompressed_size:
                    break
                    
                if i < len(self._key_list) - 1:
                    record_end = self._key_list[i + 1][0]
                else:
                    record_end = decompressed_size + offset
                index_dict["record_end"] = record_end
                i += 1
                index_dict_list.append(index_dict)
                
            offset += decompressed_size
            size_counter += compressed_size
        assert size_counter == record_block_size
        f.close()
        return index_dict_list


class MDX(MDict):
    def __init__(self, fname, encoding="", substyle=False, passcode=None):
        MDict.__init__(self, fname, encoding, passcode)
        self._substyle = substyle

    def get_index(self, check_block=True):
        index_dict_list = []
        f = open(self._fname, "rb")
        f.seek(self._record_block_offset)

        num_record_blocks = self._read_number(f)
        num_entries = self._read_number(f)
        assert num_entries == self._num_entries
        record_block_info_size = self._read_number(f)
        record_block_size = self._read_number(f)

        record_block_info_list = []
        size_counter = 0
        for i in range(num_record_blocks):
            compressed_size = self._read_number(f)
            decompressed_size = self._read_number(f)
            record_block_info_list += [(compressed_size, decompressed_size)]
            size_counter += self._number_width * 2
        assert size_counter == record_block_info_size

        offset = 0
        i = 0
        size_counter = 0
        for compressed_size, decompressed_size in record_block_info_list:
            current_pos = f.tell()
            record_block_compressed = f.read(compressed_size)
            record_block_type = record_block_compressed[:4]
            adler32 = unpack(NumberFmt.be_uint, record_block_compressed[4:8])[0]
            
            if record_block_type == b"\x00\x00\x00\x00":
                _type = 0
                if check_block:
                    record_block = record_block_compressed[8:]
            elif record_block_type == b"\x01\x00\x00\x00":
                _type = 1
                if lzo is None:
                    print("LZO compression is not supported")
                    break
                if check_block:
                    record_block = lzo.decompress(
                        record_block_compressed[8:],
                        initSize=decompressed_size,
                        blockSize=1308672,
                    )
            elif record_block_type == b"\x02\x00\x00\x00":
                _type = 2
                if check_block:
                    record_block = zlib.decompress(record_block_compressed[8:])

            if check_block:
                assert adler32 == zlib.adler32(record_block) & 0xFFFFFFFF
                assert len(record_block) == decompressed_size
                
            while i < len(self._key_list):
                index_dict = {}
                index_dict["file_pos"] = current_pos
                index_dict["compressed_size"] = compressed_size
                index_dict["decompressed_size"] = decompressed_size
                index_dict["record_block_type"] = _type
                record_start, key_text = self._key_list[i]
                index_dict["record_start"] = record_start
                index_dict["key_text"] = key_text.decode("utf-8")
                index_dict["offset"] = offset
                
                if record_start - offset >= decompressed_size:
                    break
                    
                if i < len(self._key_list) - 1:
                    record_end = self._key_list[i + 1][0]
                else:
                    record_end = decompressed_size + offset
                index_dict["record_end"] = record_end
                i += 1
                index_dict_list.append(index_dict)

            offset += decompressed_size
            size_counter += compressed_size
        f.close

        meta = {}
        meta["encoding"] = self._encoding
        meta["stylesheet"] = json.dumps(self._stylesheet)
        meta["title"] = self._title
        meta["description"] = self._description

        return {"index_dict_list": index_dict_list, "meta": meta}