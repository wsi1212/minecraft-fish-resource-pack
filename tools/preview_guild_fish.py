"""Render the guild fish and its preview; --export writes the approved texture."""
import sys
from pathlib import Path
from PIL import Image, ImageDraw

OUT = Path('/tmp/guild-fish-astra')
OUT.mkdir(exist_ok=True)


def fish():
    im = Image.new('RGBA', (30, 20))
    d = ImageDraw.Draw(im)
    ink = '#153948'
    teal_dark, teal, aqua, pale = '#24727c', '#3aaba6', '#7edbd0', '#d6f3dc'
    gold_dark, gold, gold_light = '#936035', '#db9c49', '#ffe1a0'
    # Forked, swept tail. Its two lobes stay visibly separated from the body.
    d.polygon([(1,4),(3,4),(7,7),(9,9),(9,11),(6,13),(3,16),(1,16),
               (2,13),(3,10),(2,7)], fill=ink)
    d.polygon([(2,5),(5,7),(8,9),(8,10),(5,9),(3,8)], fill=gold)
    d.line([(2,5),(4,6),(6,8)], fill=gold_light)
    d.polygon([(3,11),(7,10),(8,11),(5,13),(2,15)], fill=gold_dark)
    d.line([(3,13),(5,12),(7,11)], fill=gold)
    # Dorsal fin slopes back into the shoulder; the ventral fin is smaller.
    d.polygon([(11,7),(13,4),(17,2),(18,2),(18,6),(20,7)], fill=ink)
    d.polygon([(13,6),(15,4),(17,3),(17,6)], fill=gold)
    d.line([(14,5),(16,3),(17,3)], fill=gold_light)
    d.polygon([(14,13),(19,13),(18,16),(15,17)], fill=ink)
    d.polygon([(15,14),(18,14),(17,16)], fill=gold)
    # Rounded, tapered body. Broad colour clusters, not scattered pixels.
    d.polygon([(7,9),(9,8),(11,6),(14,5),(19,5),(22,6),(24,7),
               (26,9),(28,10),(28,11),(26,12),(24,14),(20,15),
               (15,15),(12,14),(10,12),(8,11)], fill=ink)
    d.polygon([(9,9),(12,7),(15,6),(19,6),(22,7),(25,9),(26,10),
               (26,11),(23,13),(20,14),(15,14),(12,13),(10,11)], fill=teal)
    d.polygon([(10,9),(12,7),(15,6),(19,6),(22,7),(23,8),
               (18,8),(16,9),(12,10)], fill=aqua)
    d.line([(12,7),(15,6),(19,6),(21,7)], fill=pale)
    # Creamy belly and cool underside give the fish volume even at native size.
    d.polygon([(11,11),(15,11),(18,10),(23,10),(26,11),(23,13),
               (20,14),(15,14),(12,13)], fill=pale)
    d.line([(13,13),(16,14),(20,14),(23,13)], fill='#8db9ae')
    d.line([(10,10),(12,11),(15,11)], fill=teal_dark)
    # Gill arc and a small swept pectoral fin: readable species features.
    d.line([(21,8),(20,9),(20,11),(21,12)], fill=teal_dark)
    d.polygon([(18,10),(18,12),(16,13),(16,11)], fill=gold_dark)
    d.line([(17,11),(17,12)], fill=gold_light)
    # Tiny dark eye with a single catchlight, facing to the right.
    d.rectangle((23,8,24,9), fill=ink)
    d.point((23,8), fill='#fff6db')
    d.point((27,11), fill=gold_dark)
    return im


sprite = fish()
sprite.save(OUT / 'fish.png')
# Panel is 10:16 in-world. Work on a matching 40:64 grid, avoiding the old
# square-texture cropping and horizontal stretching in the preview.
panel = Image.new('RGBA', (40,64), '#222c65')
p = ImageDraw.Draw(panel)
p.rectangle((0,0,1,63), fill='#19224f')
p.rectangle((38,0,39,63), fill='#1b2454')
p.line((2,0,37,0), fill='#3c477d')
p.line((2,63,37,63), fill='#17204c')
panel.alpha_composite(sprite, (5,22))
panel.save(OUT / 'panel.png')
if '--export' in sys.argv:
    # A power-of-two block-atlas texture. UV [0,0,10,16] samples the 40×64
    # panel at four texels per model unit, preserving square pixels in-world.
    texture = Image.new('RGBA', (64,64), '#222c65')
    texture.alpha_composite(panel, (0,0))
    texture.save(Path(__file__).parents[1] / 'assets/barkan/textures/block/guild_flag_fish.png')
# A closed, symmetric gold frame at the actual panel proportions.
framed = Image.new('RGBA', (46,70), '#73502e')
f = ImageDraw.Draw(framed)
f.rectangle((1,1,44,68), fill='#bd914c')
f.line((1,1,44,1), fill='#eed49a')
f.line((1,1,1,68), fill='#dcc082')
f.line((44,2,44,68), fill='#97703a')
framed.alpha_composite(panel, (3,3))
framed.resize((368,560), Image.Resampling.NEAREST).save(OUT / 'banner-preview.png')
sprite.resize((600,400), Image.Resampling.NEAREST).save(OUT / 'fish-detail.png')
print(OUT / 'banner-preview.png')
