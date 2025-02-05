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

import argparse, math, sys
from collections import namedtuple
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

# Convenience function to return named tuple with same name as function
def returntuple(names, *args):
    # or inspect.currentframe()
    calling_fun = sys._getframe().f_back.f_code.co_name
    return namedtuple(calling_fun, names)(*args)

# Extract xml data from the dzi file
def dzi_info(filename):
    tree = ET.parse(filename)
    root = tree.getroot()
    format = root.get('Format')
    overlap = int(root.get('Overlap'))
    tilesize = int(root.get('TileSize'))
    size = {k: int(v) for k, v in root[0].attrib.items()} # Python-sigh!
    return returntuple("format,overlap,tilesize,size",format,overlap,tilesize,size)
    
if __name__ == '__main__':
    args = get_args()
    info = dzi_info(args.input)
    print(info)

    levels = max(info.size['Height'],info.size['Width']).bit_length()
    level = levels - args.level
    print(f'Assembling from level {level} = {levels}-{args.level}')

    # Tiles wide, high
    width=math.ceil(info.size['Width']/(2**args.level))
    height=math.ceil(info.size['Height']/(2**args.level))

    # Filename: x_y.format
    max_x=math.ceil(info.size['Width']/(info.tilesize*2**args.level))
    max_y=math.ceil(info.size['Height']/(info.tilesize*2**args.level))
    print(f'Tiling {max_x}x{max_y} images of size {info.tilesize} -> {width}x{height}')

    # Tile using pivyps
    if info.overlap==0:
        tiles = [pyvips.Image.new_from_file(f"{args.input.removesuffix('.dzi')}_files/{level}/{x}_{y}.{info.format}", access="sequential")
            for y in range(max_y) for x in range(max_x)]
    else: # Overlap imposes need for cropping
        tiles = [pyvips.Image.new_from_file(f"{args.input.removesuffix('.dzi')}_files/{level}/{x}_{y}.{info.format}", access="sequential")
                .crop(info.overlap if x>0 else 0, info.overlap if y>0 else 0, 
                      info.tilesize if x+1<max_x else (width-1)%info.tilesize+1, info.tilesize if y+1<max_y else (height-1)%info.tilesize+1)
                for y in range(max_y) for x in range(max_x)]
        
    # Crop is required to trim lower right image border
    im = pyvips.Image.arrayjoin(tiles, across=max_x).crop(0,0,width,height)

    im.write_to_file(args.output)
