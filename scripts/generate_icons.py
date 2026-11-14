#!/usr/bin/env python3
"""Validate the logo artwork in assets/ and copy it into the component's Resources folder."""
import argparse
import base64
import json
from pathlib import Path
import struct
import sys
import xml.etree.ElementTree as ET
import zlib

ROOT = Path(__file__).resolve().parents[1]
NAMES = ("logo.png", "logo.svg")
XLINK = "{http://www.w3.org/1999/xlink}href"


def validate_png(png):
    """Require a well-formed 1024x1024 8-bit RGBA PNG; ancillary chunks are allowed."""
    if png[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError("logo.png is not a PNG")
    position = 8
    kinds = []
    while position < len(png):
        if position + 12 > len(png):
            raise ValueError("logo.png is truncated")
        length = struct.unpack(">I", png[position:position + 4])[0]
        kind = png[position + 4:position + 8]
        payload = png[position + 8:position + 8 + length]
        if len(payload) != length or position + 12 + length > len(png):
            raise ValueError("logo.png is truncated")
        checksum = struct.unpack(">I", png[position + 8 + length:position + 12 + length])[0]
        if checksum != zlib.crc32(kind + payload) & 0xffffffff:
            raise ValueError("logo.png has a corrupt " + kind.decode("latin-1") + " chunk")
        if not kinds and kind == b"IHDR" and struct.unpack(">IIBBBBB", payload) != (1024, 1024, 8, 6, 0, 0, 0):
            raise ValueError("logo.png must be 1024x1024 8-bit RGBA")
        kinds.append(kind)
        position += length + 12
    if not kinds or kinds[0] != b"IHDR" or kinds[-1] != b"IEND" or b"IDAT" not in kinds:
        raise ValueError("logo.png must start with IHDR, contain IDAT and end with IEND")


def validate_svg(svg, png):
    """Require PNG-in-SVG: one 64x64 <image> whose data URI is byte-identical to logo.png."""
    root = ET.fromstring(svg)
    if root.tag != "{http://www.w3.org/2000/svg}svg":
        raise ValueError("logo.svg is not an SVG document")
    if root.attrib.get("width") != "64" or root.attrib.get("height") != "64":
        raise ValueError("logo.svg must be 64x64")
    images = [element for element in root if element.tag == "{http://www.w3.org/2000/svg}image"]
    if len(images) != 1 or len(root) != 1:
        raise ValueError("logo.svg must contain exactly one embedded image")
    href = images[0].attrib.get(XLINK, images[0].attrib.get("href", ""))
    prefix = "data:image/png;base64,"
    if not href.startswith(prefix):
        raise ValueError("logo.svg must embed a PNG data URI")
    if base64.b64decode("".join(href[len(prefix):].split()), validate=True) != png:
        raise ValueError("logo.svg must embed exactly assets/logo.png")


def generate(root, check=False):
    root = Path(root)
    config = json.loads((root / "template.json").read_text())
    source = root / "assets"
    directory = root / "component" / config["repository"] / "Resources"
    png = (source / "logo.png").read_bytes()
    svg = (source / "logo.svg").read_bytes()
    validate_png(png)
    validate_svg(svg, png)
    for name, content in zip(NAMES, (png, svg)):
        path = directory / name
        if path.is_symlink():
            raise ValueError("icon destination must not be a symlink: " + str(path))
        if check:
            if not path.is_file() or path.read_bytes() != content:
                raise ValueError("icon is missing or stale: " + str(path))
        else:
            directory.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)
    return directory


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--check", action="store_true", help="verify Resources match assets without writing")
    args = parser.parse_args()
    try:
        generate(args.root, args.check)
    except (ValueError, OSError, ET.ParseError) as error:
        print(error, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
