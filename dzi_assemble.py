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

import argparse, math, sys, os, re
from collections import namedtuple
import xml.etree.ElementTree as ET
import pyvips

def get_args():
    parser = argparse.ArgumentParser(description='Extract rectangular region from Deep Zoom Image (dzi)')
    parser.add_argument('input', metavar='INPUT', help='Input image; "filename.dzi"')
    # See https://www.libvips.org/API/current/VipsForeignSave.html#vips-tiffsave for details
    parser.add_argument('output', metavar='OUTPUT', help='Output image; any vips supported format (e.g., out.tif[compression=deflate,tile,pyramid]')
    parser.add_argument('--geometry', '-g', metavar='WxH+X+Y', help='Crop part of the image (default is whole image); widhtxheight+x+y format. Coordinates are given at level 0, i.e. 1:1') # Geometry, akin to UNIX widthxheight+x+y format
    parser.add_argument('--level','-l', metavar='LEVEL', type=int, default='0', help='Subsample level (steps up from 1:1); e.g., level=2 => 2 levels up = 4x4 subsampling')
    return parser.parse_args()

def parse_geometry(geometry):
    # Expression for widhtxheight+x+y format
    pattern = r'^(\d+)x(\d+)\+(\d+)\+(\d+)$'
    match = re.match(pattern, geometry)
    if not match:
        raise argparse.ArgumentTypeError(f"Invalid geometry: '{geometry}'. Expected format: widhtxheight+x+y")
    w, h, x, y = map(int, match.groups())
    if w <= 0 or h <= 0:
        raise argparse.ArgumentTypeError("Width and height must be positive integers.")
    if x < 0 or y < 0:
        raise argparse.ArgumentTypeError("X and Y must be non-negative integers.")
    return w, h, x, y

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
    tiledir = filename.removesuffix('.dzi')+'_files'
    return returntuple("filename,tiledir,format,overlap,tilesize,size",filename,tiledir,format,overlap,tilesize,size)
    
if __name__ == '__main__':
    args = get_args()
    info = dzi_info(args.input)
    print(info)

    levels = max(info.size['Height'],info.size['Width']).bit_length()
    level = levels - args.level
    print(f'Assembling from level {level} = {levels}-{args.level}')

    # Tiles wide, high
    subsample = 2**args.level
    global_width = math.ceil(info.size['Width']/subsample)
    global_height = math.ceil(info.size['Height']/subsample)

    def _get_tile_idx(coord, subsample, tilesize):
        return int(coord // (tilesize*subsample))

    # Filename: x_y.format
    global_max_x = _get_tile_idx(info.size['Width'], subsample, info.tilesize)
    global_max_y = _get_tile_idx(info.size['Height'], subsample, info.tilesize)

    if args.geometry:
        crop_w, crop_h, crop_x, crop_y = parse_geometry(args.geometry)
        assert math.ceil((crop_x+crop_w)/subsample) <= global_width and math.ceil((crop_y+crop_h)/subsample) <= global_height, \
            "Cannot crop outside the image borders."
        min_x = _get_tile_idx(crop_x, subsample, info.tilesize)           # Extract tile of start coordinate x
        min_y = _get_tile_idx(crop_y, subsample, info.tilesize)           # Extract tile of start coordinate y
        max_x = _get_tile_idx(crop_x+crop_w, subsample, info.tilesize)    # Extract tile of end coordinate x
        max_y = _get_tile_idx(crop_y+crop_h, subsample, info.tilesize)    # Extract tile of end coordinate y
        offset_x = int(crop_x//subsample) - min_x*info.tilesize
        offset_y = int(crop_y//subsample) - min_y*info.tilesize
        width = math.ceil(crop_w/subsample)
        height = math.ceil(crop_h/subsample)
    else:
        min_x = 0
        min_y = 0
        max_x = global_max_x
        max_y = global_max_y
        offset_x = 0
        offset_y = 0
        width = global_width
        height = global_height
    print(f'Tiling {max_x-min_x+1}x{max_y-min_y+1} images of size {info.tilesize} -> {width}x{height}')

    # Tile using pivyps
    if info.overlap==0:
        tilefun = lambda x, y: (pyvips.Image.new_from_file(os.path.join(info.tiledir,str(level),f'{x}_{y}.{info.format}'), access="sequential"))
    else: # Overlap imposes need for cropping
        tilefun = lambda x, y: (pyvips.Image.new_from_file(os.path.join(info.tiledir,str(level),f'{x}_{y}.{info.format}'), access="sequential")
                                .crop(info.overlap if x>0 else 0, 
                                      info.overlap if y>0 else 0, 
                                      info.tilesize if x<global_max_x else (global_width-1)%info.tilesize+1,
                                      info.tilesize if y<global_max_y else (global_height-1)%info.tilesize+1))
    tiles = [tilefun(x, y) for y in range(min_y, max_y + 1) for x in range(min_x, max_x + 1)]

    # Crop is required to trim lower right image border
    im = pyvips.Image.arrayjoin(tiles, across=(max_x-min_x+1)).crop(offset_x,offset_y,width,height)

    im.write_to_file(args.output)
