from __future__ import print_function
from panda3d.core import loadPrcFile

loadPrcFile("cfg.prc")
from direct.showbase.AppRunnerGlobal import appRunner
from panda3d.core import Filename

if appRunner:
    path = appRunner.p3dFilename.getDirname() + '/'
else:
    path = ""
from panda3d.core import WindowProperties

wp = WindowProperties.getDefault()
wp.setOrigin(-2, -2)
wp.setTitle("Panda3D Level Editor")
WindowProperties.setDefault(wp)

from panda3d.core import *
from direct.showbase import ShowBase
from direct.showbase.DirectObject import DirectObject
from direct.filter.FilterManager import FilterManager
from camcon import CameraControler

# -------------------- Project Files Imports -----------
from buffpaint import BufferPainter
from guihelper import GuiHelper
from collisiongen import GenerateCollisionEgg
from navmeshgen import GenerateNavmeshCSV
from objectpainter import ObjectPainter
from sqliteloader import SaveScene, LoadScene
from lightmanager import LightManager
# -------------------------------

import sys
from os import makedirs
from direct.stdpy.file import listdir, exists, isdir
import random
import re


# helper function
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

cfg = {}