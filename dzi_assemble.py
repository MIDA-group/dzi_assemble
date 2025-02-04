# The DZI (Deep Zoom Image) format is an XML specification maintained by Microsoft
#  and described here: https://msdn.microsoft.com/en-us/library/cc645077(v=vs.95).aspx

# Example
#<?xml version="1.0" encoding="UTF-8"?>
#<Image xmlns="http://schemas.microsoft.com/deepzoom/2008"
#   Format="jpg" 
#   Overlap="2" 
#   TileSize="256" >
#   <Size Height="9221" 
#         Width="7026"/>
#</Image>

import argparse
import math
import xml.etree.ElementTree as ET
import pyvips

def get_args():
    parser = argparse.ArgumentParser(description='Extract rectangular region from Deep Zoom Image (dzi)')
    parser.add_argument('input', metavar='INPUT', help='Input image; "filename.dzi"')
    # See https://www.libvips.org/API/current/VipsForeignSave.html#vips-tiffsave for details
    parser.add_argument('output', metavar='OUTPUT', help='Output image; any vips supported format (e.g., out.tif[compression=deflate,tile,pyramid]')
    # Todo
    #parser.add_argument('--geometry', '-g', metavar='WxH+X+Y', help='Crop part of the image (default is whole image); widhtxheight+x+y format') # Geometry, akin to UNIX widthxheight+x+y format
    parser.add_argument('--level','-l', metavar='LEVEL', type=int, default='0', help='Subsample level (steps up from 1:1); e.g., level=2 => 2 levels up = 4x4 subsampling')
    return parser.parse_args()


if __name__ == '__main__':
    args = get_args()

    tree = ET.parse(args.input)
    root = tree.getroot()
    format = root.get('Format')
    overlap = int(root.get('Overlap'))
    tilesize = int(root.get('TileSize'))
    imgsize = {k: int(v) for k, v in root[0].attrib.items()} # Python-sigh!
    print(overlap,tilesize,imgsize)

    levels = max(imgsize['Height'],imgsize['Width']).bit_length()
    level = levels - args.level
    print(levels, level)

    width=math.ceil(imgsize['Width']/(2**args.level))
    height=math.ceil(imgsize['Height']/(2**args.level))

    # Filename: x_y.format
    max_x=math.ceil(imgsize['Width']/(tilesize*2**args.level))
    max_y=math.ceil(imgsize['Height']/(tilesize*2**args.level))
    print(f'Tiling {max_x}x{max_y} images of size {tilesize} -> {width}x{height}')

    if overlap==0:
        tiles = [pyvips.Image.new_from_file(f"{args.input.removesuffix('.dzi')}_files/{level}/{x}_{y}.{format}", access="sequential")
            for y in range(max_y) for x in range(max_x)]
    else: # Overlap imposes need for cropping
        tiles = [pyvips.Image.new_from_file(f"{args.input.removesuffix('.dzi')}_files/{level}/{x}_{y}.{format}", access="sequential")
                .crop(overlap if x>0 else 0, overlap if y>0 else 0, 
                      tilesize if x+1<max_x else (width-1)%tilesize+1, tilesize if y+1<max_y else (height-1)%tilesize+1)
                for y in range(max_y) for x in range(max_x)]
        
    # Crop required to trim lower right image border
    im = pyvips.Image.arrayjoin(tiles, across=max_x).crop(0,0,width,height)

    im.write_to_file(args.output)
