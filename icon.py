#!/usr/bin/env python3
"""Generate TigerTerminal.icns — Tiger-compatible (raw pixel format).

Tiger (10.4) does NOT support PNG-in-icns. It needs the old raw formats:
  is32/s8mk — 16x16 RGB + alpha mask
  il32/l8mk — 32x32 RGB + alpha mask
  it32/t8mk — 128x128 RLE-compressed RGB + alpha mask

Requires: Pillow
Output: TigerTerminal.icns
"""
import struct
import io
from PIL import Image, ImageDraw, ImageFont


def draw_icon(size):
    """Draw terminal icon at given pixel size."""
    img = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    margin = int(size * 0.06)
    radius = int(size * 0.18)
    box = (margin, margin, size - margin, size - margin)

    bg_color = (30, 30, 46, 255)
    border_color = (49, 50, 68, 255)

    draw.rounded_rectangle(box, radius=radius, fill=bg_color,
                           outline=border_color, width=max(1, size // 64))

    # Title bar dots
    dot_y = margin + int(size * 0.12)
    dot_r = max(2, int(size * 0.03))
    dot_spacing = int(size * 0.07)
    dot_x_start = margin + int(size * 0.10)

    colors = [(243, 139, 168), (249, 226, 175), (166, 227, 161)]
    for i, color in enumerate(colors):
        cx = dot_x_start + i * dot_spacing
        draw.ellipse((cx - dot_r, dot_y - dot_r, cx + dot_r, dot_y + dot_r),
                     fill=color + (255,))

    # Separator line
    sep_y = dot_y + int(size * 0.08)
    draw.line((margin + radius // 2, sep_y, size - margin - radius // 2, sep_y),
              fill=border_color, width=max(1, size // 128))

    # ">_" prompt
    font_size = int(size * 0.35)
    font = None
    for font_name in ['/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf',
                       '/usr/share/fonts/truetype/liberation/LiberationMono-Bold.ttf',
                       'DejaVuSansMono-Bold.ttf', 'LiberationMono-Bold.ttf']:
        try:
            font = ImageFont.truetype(font_name, font_size)
            break
        except (OSError, IOError):
            continue
    if font is None:
        font = ImageFont.load_default()

    content_top = sep_y + int(size * 0.05)
    content_bottom = size - margin
    content_height = content_bottom - content_top

    prompt_text = ">_"
    bbox = draw.textbbox((0, 0), prompt_text, font=font)
    tw = bbox[2] - bbox[0]
    th = bbox[3] - bbox[1]
    tx = (size - tw) // 2
    ty = content_top + (content_height - th) // 2

    prompt_color = (166, 227, 161, 255)
    draw.text((tx, ty), prompt_text, fill=prompt_color, font=font)

    # Cursor block
    cursor_x = tx + tw + int(size * 0.03)
    cursor_w = max(2, int(size * 0.06))
    cursor_h = th
    cursor_color = (137, 180, 250, 180)
    draw.rectangle((cursor_x, ty, cursor_x + cursor_w, ty + cursor_h),
                   fill=cursor_color)

    return img


def rle_compress_channel(data):
    """RLE-compress a single channel for it32.

    Format: control byte + data
      control >= 128: repeat (control - 125) times the next byte
      control < 128:  copy (control + 1) literal bytes
    """
    result = bytearray()
    i = 0
    n = len(data)

    while i < n:
        # Look for a run of identical bytes
        run_start = i
        while i + 1 < n and data[i] == data[i + 1] and i - run_start < 129:
            i += 1

        run_len = i - run_start + 1

        if run_len >= 3:
            # Encode as repeat: control = run_len + 125
            result.append(run_len + 125)
            result.append(data[run_start])
            i = run_start + run_len
        else:
            # Encode as literal run — look ahead for non-repeating bytes
            i = run_start
            lit_start = i
            while i < n:
                # Check if next 3+ bytes are a run (worth switching to repeat)
                if i + 2 < n and data[i] == data[i + 1] == data[i + 2]:
                    break
                i += 1
                if i - lit_start >= 128:
                    break

            lit_len = i - lit_start
            if lit_len > 0:
                result.append(lit_len - 1)
                result.extend(data[lit_start:lit_start + lit_len])

    return bytes(result)


def img_to_raw_rgb(img):
    """Extract raw RGB bytes (no alpha) from RGBA image."""
    pixels = img.tobytes()
    rgb = bytearray()
    for i in range(0, len(pixels), 4):
        rgb.append(pixels[i])      # R
        rgb.append(pixels[i + 1])  # G
        rgb.append(pixels[i + 2])  # B
    return bytes(rgb)


def img_to_alpha(img):
    """Extract 8-bit alpha mask from RGBA image."""
    return img.split()[3].tobytes()


def img_to_channels(img):
    """Split RGBA image into separate R, G, B channel byte arrays."""
    pixels = img.tobytes()
    r_chan = bytearray()
    g_chan = bytearray()
    b_chan = bytearray()
    for i in range(0, len(pixels), 4):
        r_chan.append(pixels[i])
        g_chan.append(pixels[i + 1])
        b_chan.append(pixels[i + 2])
    return bytes(r_chan), bytes(g_chan), bytes(b_chan)


def img_to_1bit(img, size):
    """Convert RGBA image to 1-bit bitmap (for ICN#).
    Returns icon data + mask data (each size*size/8 bytes)."""
    pixels = img.load()
    icon_bits = bytearray()
    mask_bits = bytearray()

    for y in range(size):
        icon_byte = 0
        mask_byte = 0
        for x in range(size):
            r, g, b, a = pixels[x, y]
            # Icon: pixel is "on" if it's not too dark
            lum = (r + g + b) // 3
            if lum > 64 and a > 128:
                icon_byte |= (1 << (7 - (x % 8)))
            # Mask: pixel is visible if alpha > 128
            if a > 128:
                mask_byte |= (1 << (7 - (x % 8)))
            if (x % 8) == 7:
                icon_bits.append(icon_byte)
                mask_bits.append(mask_byte)
                icon_byte = 0
                mask_byte = 0

    return bytes(icon_bits) + bytes(mask_bits)


def build_icns(entries):
    """Build .icns from list of (type_code_str, data_bytes)."""
    body = b''
    for type_code, data in entries:
        entry = type_code.encode('ascii') + struct.pack('>I', len(data) + 8) + data
        body += entry
    header = b'icns' + struct.pack('>I', len(body) + 8)
    return header + body


def main():
    entries = []

    # ── 16×16: is32 + s8mk ──
    img16 = draw_icon(16)
    entries.append(('is32', img_to_raw_rgb(img16)))
    entries.append(('s8mk', img_to_alpha(img16)))

    # ── 32×32: ICN# + il32 + l8mk ──
    img32 = draw_icon(32)
    entries.append(('ICN#', img_to_1bit(img32, 32)))
    entries.append(('il32', img_to_raw_rgb(img32)))
    entries.append(('l8mk', img_to_alpha(img32)))

    # ── 128×128: it32 + t8mk ──
    img128 = draw_icon(128)
    r, g, b = img_to_channels(img128)
    it32_data = b'\x00\x00\x00\x00'  # 4-byte header
    it32_data += rle_compress_channel(r)
    it32_data += rle_compress_channel(g)
    it32_data += rle_compress_channel(b)
    entries.append(('it32', it32_data))
    entries.append(('t8mk', img_to_alpha(img128)))

    icns_data = build_icns(entries)

    with open('TigerTerminal.icns', 'wb') as f:
        f.write(icns_data)

    print(f'Created TigerTerminal.icns ({len(icns_data)} bytes)')

    # Breakdown
    for type_code, data in entries:
        print(f'  {type_code}: {len(data)} bytes')

    # Preview PNG
    preview = draw_icon(256)
    preview.save('icon_preview.png')
    print('Saved icon_preview.png')


if __name__ == '__main__':
    main()
