#!/usr/bin/env python3
import sys, time, argparse
from pathlib import Path

try:
    from PIL import Image as PILImage
except ImportError:
    print("ERROR: Pillow not installed. Run: pip install Pillow")
    sys.exit(1)

try:
    from fontTools.fontBuilder import FontBuilder
    from fontTools.pens.ttGlyphPen import TTGlyphPen
    from fontTools.ttLib.tables._g_l_y_f import Glyph
    from fontTools.misc.timeTools import epoch_diff
    from fontTools.ttLib.tables.D_S_I_G_ import table_D_S_I_G_
    from fontTools.ttLib.tables._g_a_s_p import table__g_a_s_p
except ImportError:
    print("ERROR: fonttools not installed. Run: pip install fonttools")
    sys.exit(1)

parser = argparse.ArgumentParser(description="Bitmap PNG font -> TTF")
parser.add_argument("--png",          required=True)
parser.add_argument("--cell-w",       type=int, default=9)
parser.add_argument("--cell-h",       type=int, default=16)
parser.add_argument("--cols",         type=int, default=16)
parser.add_argument("--start",        type=int, default=32)
parser.add_argument("--spacing",      type=int, default=0)
parser.add_argument("--word-spacing", type=int, default=4)
parser.add_argument("--scale",        type=int, default=64)
parser.add_argument("--name",         type=str, default="BitmapFont")
parser.add_argument("--output",       type=str, default=None)
parser.add_argument("--threshold",    type=int, default=128)
args = parser.parse_args()

png_path = Path(args.png)
if not png_path.exists():
    print("ERROR: Cannot find %s" % png_path)
    sys.exit(1)

img = PILImage.open(png_path).convert("RGBA")
img_w, img_h = img.size
pixels = img.load()

CELL_W        = args.cell_w
CELL_H        = args.cell_h
COLS          = args.cols
START         = args.start
SCALE         = args.scale
SPACING       = args.spacing
WORD_SPACING  = args.word_spacing
THRESHOLD     = args.threshold
NAME          = args.name

UNITS     = CELL_H * SCALE
ASCENDER  = int(UNITS * 0.8)
DESCENDER = -(UNITS - ASCENDER)
total_glyphs = (img_w // CELL_W) * (img_h // CELL_H)

print("PNG: %dx%dpx -> %d glyph cells (%dx%d)" % (img_w, img_h, total_glyphs, CELL_W, CELL_H))

def draw_glyph(ox, oy, cell_w, cell_h, scale):
    pen = TTGlyphPen(None)
    has_ink = False
    advance = 1
    for row_idx in range(cell_h):
        y_top = (cell_h - row_idx) * scale
        y_bot = (cell_h - row_idx - 1) * scale
        for col in range(cell_w):
            px, py = ox + col, oy + row_idx
            if px >= img_w or py >= img_h:
                continue
            r, g, b, a = pixels[px, py]
            if a > THRESHOLD:
                x0, x1 = col * scale, (col + 1) * scale
                pen.moveTo((x0, y_bot)); pen.lineTo((x1, y_bot))
                pen.lineTo((x1, y_top)); pen.lineTo((x0, y_top))
                pen.closePath()
                has_ink = True
                if (col + 1) > advance:
                    advance = col + 1
    if not has_ink:
        g = Glyph(); g.numberOfContours = 0; return g, max(cell_w // 2, 1)
    return pen.glyph(), advance + 1

def make_notdef(cell_w, cell_h, scale):
    pen = TTGlyphPen(None)
    w, h, m = cell_w*scale, cell_h*scale, scale
    pen.moveTo((0,0)); pen.lineTo((w,0)); pen.lineTo((w,h)); pen.lineTo((0,h)); pen.closePath()
    pen.moveTo((m,m)); pen.lineTo((m,h-m)); pen.lineTo((w-m,h-m)); pen.lineTo((w-m,m)); pen.closePath()
    return pen.glyph()

glyph_order = [".notdef"]
cmap_map, metrics, glyphs = {}, {}, {}
glyphs[".notdef"]  = make_notdef(CELL_W, CELL_H, SCALE)
metrics[".notdef"] = (CELL_W * SCALE, 0)

for i in range(total_glyphs):
    code = START + i
    if code > 126:
        break
    col, row = i % COLS, i // COLS
    ox, oy   = col * CELL_W, row * CELL_H
    name     = "uni%04X" % code
    glyph, raw_adv = draw_glyph(ox, oy, CELL_W, CELL_H, SCALE)

    # Space character uses word spacing
    if code == 32:
        adv = max(WORD_SPACING * SCALE, SCALE)
    else:
        adv = max((raw_adv * SCALE) + (SPACING * SCALE // max(CELL_W, 1)), SCALE)

    glyph_order.append(name)
    glyphs[name]   = glyph
    metrics[name]  = (adv, 0)
    cmap_map[code] = name

fb = FontBuilder(UNITS, isTTF=True)
fb.setupGlyphOrder(glyph_order)
fb.setupCharacterMap(cmap_map)
fb.setupGlyf(glyphs)
fb.setupHorizontalMetrics(metrics)
fb.setupHorizontalHeader(ascent=ASCENDER, descent=DESCENDER)
fb.setupNameTable({
    "familyName": NAME,
    "styleName":  "Regular",
    "fullName":   NAME + " Regular",
    "psName":     NAME.replace(" ", "") + "-Regular",
    "version":    "Version 1.000",
    "copyright":  "Generated from " + png_path.name,
})
fb.setupOS2(
    sTypoAscender=ASCENDER, sTypoDescender=DESCENDER,
    usWinAscent=ASCENDER,   usWinDescent=abs(DESCENDER),
    sxHeight=int(ASCENDER*0.5), sCapHeight=ASCENDER,
    fsType=0, achVendID="NONE", fsSelection=0x0040,
)
fb.setupPost(isFixedPitch=0, formatType=2.0)
fb.setupHead(unitsPerEm=UNITS)

now = int(time.time()) - epoch_diff
fb.font["head"].created  = now
fb.font["head"].modified = now
fb.font["head"].macStyle = 0
fb.font["head"].flags    = 0b0000000000001011
fb.font["OS/2"].version  = 4
fb.font["OS/2"].fsSelection = 0x0040

gasp = table__g_a_s_p()
gasp.version = 1; gasp.gaspRange = {65535: 0x000F}
fb.font["gasp"] = gasp

dsig = table_D_S_I_G_()
dsig.ulVersion = 1; dsig.usFlag = 1; dsig.usNumSigs = 0; dsig.signatureRecords = []
fb.font["DSIG"] = dsig

out = Path(args.output) if args.output else png_path.with_suffix(".ttf")
fb.font.save(str(out))
print("Saved: %s  (%d glyphs)" % (out, len(glyphs)-1))
