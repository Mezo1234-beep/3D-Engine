from panda3d.core import BitMask32
import re


def sort_nicely(l):
    convert = lambda text: int(text) if text.isdigit() else text
    alphanum_key = lambda key: [convert(c) for c in re.split('([0-9]+)', key)]
    l.sort(key=alphanum_key)


def convertToPatches(model):
    """ Converts a model to patches. This is required before being able
    to use it with tesselation shaders """
    # self.debug("Converting model to patches ..")
    for node in model.find_all_matches("**/+GeomNode"):
        geom_node = node.node()
        num_geoms = geom_node.get_num_geoms()
        for i in range(num_geoms):
            geom_node.modify_geom(i).make_patches_in_place()


BUFFER_HEIGHT = 0
BUFFER_ATR = 1
BUFFER_GRASS = 2
BUFFER_WALK = 3
BUFFER_ATR2 = 4

MODE_HEIGHT = 0
MODE_TEXTURE = 1
MODE_GRASS = 2
MODE_OBJECT = 3
MODE_WALK = 4

OBJECT_MODE_ONE = 0
OBJECT_MODE_MULTI = 1
OBJECT_MODE_WALL = 2
OBJECT_MODE_SELECT = 3
OBJECT_MODE_ACTOR = 4
OBJECT_MODE_COLLISION = 5
OBJECT_MODE_PICKUP = 6

HEIGHT_MODE_UP = 0
HEIGHT_MODE_DOWN = 1
HEIGHT_MODE_LEVEL = 2
HEIGHT_MODE_BLUR = 3

WALK_MODE_NOWALK = 0
WALK_MODE_WALK = 1

GRASS_MODE_PAINT = 1
GRASS_MODE_REMOVE = 0

MASK_WATER = BitMask32.bit(1)
MASK_SHADOW = BitMask32.bit(2)
MASK_TERRAIN_ONLY = BitMask32.bit(3)
