"""Local incident composites: source above a non-overlapping corrected-ROI grid."""
import io
import math
from PIL import Image, ImageDraw, ImageFont
from .imaging import rectify


def rule_variables(node):
    if 'group' in node:
        return set().union(*(rule_variables(child) for child in node['children']))
    return {node['variable']}


def incident_snapshot(frame, regions):
    source = Image.fromarray(frame[:, :, ::-1])
    source.thumbnail((1280, 720))
    columns = min(4, max(1, len(regions)))
    width = max(source.width, columns * 320)
    height = source.height + math.ceil(len(regions) / columns) * 200
    canvas = Image.new('RGB', (width, height), 'white')
    canvas.paste(source, (0, 0))
    draw = ImageDraw.Draw(canvas)
    font = ImageFont.load_default(size=18)
    tile_width = width // columns
    for i, region in enumerate(regions):
        color = ('#d62728', '#167b3b', '#1967d2', '#8e24aa')[i % 4]
        points = [(int(x * (source.width-1)), int(y * (source.height-1))) for x,y in region.corners]
        draw.line(points + [points[0]], fill=color, width=3)
        draw.text(points[0], str(i+1), fill=color, font=font)
        _, corrected = rectify(frame, region)
        crop = Image.fromarray(corrected[:, :, ::-1])
        scale = min((tile_width-16)/crop.width, 170/crop.height)
        crop = crop.resize((max(1,round(crop.width*scale)), max(1,round(crop.height*scale))), Image.Resampling.LANCZOS)
        x, y = (i % columns)*tile_width, source.height+(i//columns)*200
        draw.text((x+8,y+4), f'{i+1}. {region.name[:28]}', fill=color, font=font)
        canvas.paste(crop,(x+8+(tile_width-16-crop.width)//2,y+24+(170-crop.height)//2))
    output=io.BytesIO()
    canvas.save(output,format='JPEG',quality=88)
    return output.getvalue()
