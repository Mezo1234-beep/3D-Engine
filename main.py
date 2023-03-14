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

from os import makedirs
from direct.stdpy.file import listdir, exists, isdir
import random

# -------------------------------
from helper import *
from cfg import loadcfg, cfg


class Editor(DirectObject):

    def __init__(self):
        # load default values
        super().__init__()
        loadcfg()

        # init ShowBase
        base = ShowBase.ShowBase()
        render.hide(MASK_TERRAIN_ONLY)
        base.enableParticles()
        # PStatClient.connect()

        # manager for post process filters (fxaa, soft shadows, dof)
        manager = FilterManager(base.win, base.cam)
        fxaa_only = True
        if cfg['filters'] == 2:
            fxaa_only = False
        self.filters = self.setupFilters(manager, fxaa_only=fxaa_only)

        # manager for point lights
        self.light_manager = LightManager()
        # self.light_manager.addLight((256.0, 256.0, 30.0), (1.0, 0.0, 0.0), 40.0)

        # make a grid
        self.init_grid()

        # axis to help orient the scene
        self.init_axis()

        # store variables needed for diferent classes
        self.init_gerneral_variables()

        # camera control
        self.init_camera()

        # painter
        self.init_painter()

        # GUI
        self.init_gui()

        # object painter
        self.objectPainter = ObjectPainter(self.light_manager)

        # terrain mesh the 80k mesh loads to slow from egg, using bam self.mesh=loader.loadModel('data/mesh80k.egg')
        # #there's also a 3k, 10k and 35k mesh (can be broken at this point!)

        self.init_mesh()

        # grass
        self.init_grass()

        # skydome
        self.init_sky()

        # waterplane
        self.init_water()

        # light
        # sun
        self.init_light()

        # fog
        # rgb color + coefficiency in alpha
        render.setShaderInput("fog", Vec4(0.4, 0.4, 0.4, 0.002))

        self.set_keys()

        # make sure things have some/any starting value
        self.set_init_values()

        # tasks
        taskMgr.add(self.perFrameUpdate, 'perFrameUpdate_task', sort=46)
        # self.clock=12.0
        # taskMgr.doMethodLater(.1, self.clockTick,'clock_task')

    # -------------- initializing ------------------

    def init_grid(self):
        cm = CardMaker("plane")
        cm.setFrame(0, 512, 0, 512)
        self.grid = render.attachNewNode(cm.generate())
        self.grid.lookAt(0, 0, -1)
        self.grid.setTexture(loader.loadTexture('data/grid.png'))
        self.grid.setTransparency(TransparencyAttrib.MDual)
        self.grid.setTexScale(TextureStage.getDefault(), 16, 16, 1)
        self.grid.setZ(25.5)
        self.grid.setLightOff()
        self.grid.setColor(0, 0, 0, 0.5)
        self.grid_z = 25.5
        self.grid_scale = 16
        self.grid.hide(MASK_WATER)
        self.grid.hide(MASK_SHADOW)
        # self.grid.hide()

    def init_axis(self):
        self.axis = loader.loadModel('data/axis.egg')
        self.axis.reparentTo(render)
        self.axis.setLightOff()
        self.axis.hide(MASK_WATER)
        self.axis.hide(MASK_SHADOW)
        self.axis.setShader(Shader.load(Shader.SLGLSL, cfg["shader_editor_v"], cfg["shader_editor_f"]))

    def init_gerneral_variables(self):
        self.skyimg = PNMImage(cfg['sky_color'])
        self.mode = MODE_HEIGHT
        self.height_mode = HEIGHT_MODE_UP
        self.tempColor = 1
        self.tempAlpha = 0.05
        self.ignoreHover = False
        self.collision_mesh = None
        self.winsize = [0, 0]
        self.object_mode = OBJECT_MODE_ONE
        self.hpr_axis = 'H: '
        self.last_model_path = ''
        self.lastUpdateTime = 0.0
        self.curent_textures = [0, 1, 2, 3, 4, 5]
        self.textures_diffuse = []
        self.textures_normal = []
        self.grass_textures = []
        self.current_grass_textures = [0, 1, 2]
        self.last_object_index = 0

    def init_camera(self):
        base.disableMouse()
        self.controler = CameraControler(cfg)
        self.controler.cameraNode.setZ(25.5)
        render.setShaderInput('camera', base.cam)

    def init_painter(self):
        self.brushList = []
        dirList = listdir(Filename(path + cfg['brush_dir']).toOsSpecific())
        for fname in dirList:
            if Filename(fname).getExtension() in ('png', 'tga', 'dds'):
                self.brushList.append(cfg['brush_dir'] + fname)

        self.painter = BufferPainter(self.brushList, showBuff=False)
        # BUFFER_HEIGHT
        self.painter.addCanvas(size=cfg['h_map_size'],
                               default_tex=cfg['h_map_def'],
                               brush_shader=Shader.load(Shader.SLGLSL, "shaders/brush_v.glsl", "shaders/brush_f.glsl"),
                               shader_inputs={"use_map": 0.0})
        # BUFFER_ATR
        self.painter.addCanvas(size=cfg['a_map_size'], default_tex=cfg['a_map_def'])
        # BUFFER_GRASS
        self.painter.addCanvas(size=cfg['g_map_size'])
        # BUFFER_WALK =3
        self.painter.addCanvas(size=cfg['w_map_size'], brush_shader=Shader.load(Shader.SLGLSL, "shaders/brush3_v.glsl",
                                                                                "shaders/brush3_f.glsl"))
        # BUFFER_ATR2=4
        self.painter.addCanvas(size=cfg['a_map_size'])

        # gl selection
        if cfg['use_gl_select']:
            self.painter.setup_gl_select(self.painter.textures[BUFFER_HEIGHT])

    def init_gui(self):
        self.gui = GuiHelper(path, cfg['theme'])
        # tooltip bar
        self.tooltip = self.gui.addTooltip(self.gui.BottomLeft, (564, 32), y_offset=-96)
        self.tooltip.hide()
        # the toolbar_id here is just an int, not a 'toolbar object'!
        self.toolbar_id = self.gui.addToolbar(self.gui.TopLeft, (864, 32), icon_size=48,
                                              hover_command=self.onToolbarHover, color=(1, 1, 1, 0.0))
        id = 0
        for brush in self.brushList:
            self.gui.addButton(self.toolbar_id, brush, self.setBrush, [id], tooltip=self.tooltip,
                               tooltip_text='Set Brush Shape', back_icon=cfg['theme'] + '/icon.png')
            id += 1
        # texture palette
        self.palette_id = self.gui.addToolbar(self.gui.TopRight, (80, 512), icon_size=80, x_offset=-80, y_offset=0,
                                              hover_command=self.onToolbarHover)
        dirList = listdir(Filename(path + cfg['dif_tex_dir']).toOsSpecific())
        for fname in dirList:
            if Filename(fname).getExtension() in ('dds'):
                self.textures_diffuse.append(fname)
                self.textures_normal.append(fname)
        # sort them, we want 0,1,2,3,4,5 as default textures
        sort_nicely(self.textures_diffuse)
        sort_nicely(self.textures_normal)
        for tex in self.textures_diffuse:
            id = self.textures_diffuse.index(tex)
            self.textures_diffuse[id] = cfg['dif_tex_dir'] + tex
        for tex in self.textures_normal:
            id = self.textures_normal.index(tex)
            self.textures_normal[id] = cfg['nrm_tex_dir'] + tex

        self.gui.addButton(self.palette_id, self.textures_diffuse[0], self.setAtrMapColor,
                           [(1.0, 0.0, 0.0, 1.0), (0.0, 0.0, 0.0, 1.0)], tooltip=self.tooltip,
                           tooltip_text='Set Brush Texture')
        self.gui.addButton(self.palette_id, self.textures_diffuse[1], self.setAtrMapColor,
                           [(0.0, 1.0, 0.0, 1.0), (0.0, 0.0, 0.0, 1.0)], tooltip=self.tooltip,
                           tooltip_text='Set Brush Texture')
        self.gui.addButton(self.palette_id, self.textures_diffuse[2], self.setAtrMapColor,
                           [(0.0, 0.0, 1.0, 1.0), (0.0, 0.0, 0.0, 1.0)], tooltip=self.tooltip,
                           tooltip_text='Set Brush Texture')
        self.gui.addButton(self.palette_id, self.textures_diffuse[3], self.setAtrMapColor,
                           [(0.0, 0.0, 0.0, 1.0), (1.0, 0.0, 0.0, 1.0)], tooltip=self.tooltip,
                           tooltip_text='Set Brush Texture')
        self.gui.addButton(self.palette_id, self.textures_diffuse[4], self.setAtrMapColor,
                           [(0.0, 0.0, 0.0, 1.0), (0.0, 1.0, 0.0, 1.0)], tooltip=self.tooltip,
                           tooltip_text='Set Brush Texture')
        self.gui.addButton(self.palette_id, self.textures_diffuse[5], self.setAtrMapColor,
                           [(0.0, 0.0, 0.0, 1.0), (0.0, 0.0, 1.0, 1.0)], tooltip=self.tooltip,
                           tooltip_text='Set Brush Texture')

        self.gui.addFloatingButton(self.palette_id, [32, 32], cfg['theme'] + '/change.png', [48, 48], self.changeTex,
                                   [0], tooltip=self.tooltip, tooltip_text='Change texture')
        self.gui.addFloatingButton(self.palette_id, [32, 32], cfg['theme'] + '/change.png', [48, 128], self.changeTex,
                                   [1], tooltip=self.tooltip, tooltip_text='Change texture')
        self.gui.addFloatingButton(self.palette_id, [32, 32], cfg['theme'] + '/change.png', [48, 208], self.changeTex,
                                   [2], tooltip=self.tooltip, tooltip_text='Change texture')
        self.gui.addFloatingButton(self.palette_id, [32, 32], cfg['theme'] + '/change.png', [48, 288], self.changeTex,
                                   [3], tooltip=self.tooltip, tooltip_text='Change texture')
        self.gui.addFloatingButton(self.palette_id, [32, 32], cfg['theme'] + '/change.png', [48, 368], self.changeTex,
                                   [4], tooltip=self.tooltip, tooltip_text='Change texture')
        self.gui.addFloatingButton(self.palette_id, [32, 32], cfg['theme'] + '/change.png', [48, 448], self.changeTex,
                                   [5], tooltip=self.tooltip, tooltip_text='Change texture')

        # grass 'palette'
        self.grass_toolbar_id = self.gui.addToolbar(self.gui.TopRight, (80, 512), icon_size=80, x_offset=-80,
                                                    y_offset=0, hover_command=self.onToolbarHover)
        dirList = listdir(Filename(path + cfg['grs_tex_dir']).toOsSpecific())
        for fname in dirList:
            if Filename(fname).getExtension() in ('dds', 'png'):
                self.grass_textures.append(cfg['grs_tex_dir'] + fname)
        sort_nicely(self.grass_textures)
        self.gui.addButton(self.grass_toolbar_id, self.grass_textures[0], self.setGrassMapColor, [(1.0, 0.0, 0.0, 1.0)],
                           tooltip=self.tooltip, tooltip_text='Set Grass Texture', back_icon=cfg['theme'] + '/icon.png')
        self.gui.addButton(self.grass_toolbar_id, self.grass_textures[1], self.setGrassMapColor, [(0.0, 1.0, 0.0, 1.0)],
                           tooltip=self.tooltip, tooltip_text='Set Grass Texture', back_icon=cfg['theme'] + '/icon.png')
        self.gui.addButton(self.grass_toolbar_id, self.grass_textures[2], self.setGrassMapColor, [(0.0, 0.0, 1.0, 1.0)],
                           tooltip=self.tooltip, tooltip_text='Set Grass Texture', back_icon=cfg['theme'] + '/icon.png')
        self.gui.addButton(self.grass_toolbar_id, cfg['theme'] + '/del.png', self.setGrassMapColor,
                           [(0.0, 0.0, 0.0, 1.0)], tooltip=self.tooltip, tooltip_text='Remove Grass',
                           back_icon=cfg['theme'] + '/icon.png')
        self.gui.addFloatingButton(self.grass_toolbar_id, [32, 32], cfg['theme'] + '/change.png', [48, 48],
                                   self.changeGrassTex, [0], tooltip=self.tooltip, tooltip_text='Change texture')
        self.gui.addFloatingButton(self.grass_toolbar_id, [32, 32], cfg['theme'] + '/change.png', [48, 128],
                                   self.changeGrassTex, [1], tooltip=self.tooltip, tooltip_text='Change texture')
        self.gui.addFloatingButton(self.grass_toolbar_id, [32, 32], cfg['theme'] + '/change.png', [48, 208],
                                   self.changeGrassTex, [2], tooltip=self.tooltip, tooltip_text='Change texture')
        self.gui.hideElement(self.grass_toolbar_id)

        # save/load
        self.gui.addSaveLoadDialog(self.save, self.load, self.hideSaveMenu)
        # config
        self.gui.addConfigDialog(self.configBrush)
        # sky/sea dialog
        self.gui.addSkySeaDialog(self.configSkySea)

        # extra tools and info at the bottom
        self.statusbar = self.gui.addToolbar(self.gui.BottomLeft, (704, 128), icon_size=64, y_offset=-64,
                                             hover_command=self.onToolbarHover, color=(1, 1, 1, 0.2))
        self.size_info = self.gui.addInfoIcon(self.statusbar, cfg['theme'] + '/resize.png', '1.0', tooltip=self.tooltip,
                                              tooltip_text='Brush Size or Object Scale:   [A]-Decrease    [D]-Increase',
                                              slider_cmd=self.setSize, slider_range=(0.1, 10.0))
        self.color_info = self.gui.addInfoIcon(self.statusbar, cfg['theme'] + '/color.png', '0.05',
                                               tooltip=self.tooltip,
                                               tooltip_text='Brush Strength or Object Z offset:   [W]-Increase   [S]-Decrease',
                                               slider_cmd=self.setStrength, slider_range=(0.0, 1.0))
        self.heading_info = self.gui.addInfoIcon(self.statusbar, cfg['theme'] + '/rotate.png', '0',
                                                 tooltip=self.tooltip,
                                                 tooltip_text='Rotation ([1][2][3] to change axis in Object Mode):   [Q]-Left   [E]-Right',
                                                 slider_cmd=self.setHeading, slider_range=(0.0, 360.0))
        self.gui.addButton(self.statusbar, cfg['theme'] + '/config.png', self.configBrush, [True], self.tooltip,
                           'Configure brush and grid (numeric values)')
        self.gui.addButton(self.statusbar, cfg['theme'] + '/hm_icon.png', self.setMode, [MODE_HEIGHT], self.tooltip,
                           'Paint Heightmap Mode [F1]')
        self.gui.addButton(self.statusbar, cfg['theme'] + '/tex_icon.png', self.setMode, [MODE_TEXTURE], self.tooltip,
                           'Paint Texture Mode [F2]')
        self.gui.addButton(self.statusbar, cfg['theme'] + '/grass.png', self.setMode, [MODE_GRASS], self.tooltip,
                           'Paint Grass Mode [F3]')
        self.gui.addButton(self.statusbar, cfg['theme'] + '/place_icon.png', self.setMode, [MODE_OBJECT], self.tooltip,
                           'Paint Objects Mode [F4]')
        self.gui.addButton(self.statusbar, cfg['theme'] + '/walkmap_icon.png', self.setMode, [MODE_WALK], self.tooltip,
                           'Paint Walkmap Mode [F5]')
        self.gui.addButton(self.statusbar, cfg['theme'] + '/sky_sea_icon.png', self.configSkySea, [True],
                           tooltip=self.tooltip,
                           tooltip_text='Configure stone and sea and sky (and all that they encompass) [F6]')
        self.gui.addButton(self.statusbar, cfg['theme'] + '/save.png', self.showSaveMenu, tooltip=self.tooltip,
                           tooltip_text='Save/Load [F7]')
        # gray out buttons
        self.gui.grayOutButtons(self.statusbar, (4, 10), None)

        # object toolbars (scrollable)
        # each object paint mode has its own
        self.object_toolbar_id = self.gui.addScrolledToolbar(self.gui.TopRight, 192, (192, 6000), x_offset=-192,
                                                             y_offset=128, hover_command=self.onToolbarHover,
                                                             color=(0, 0, 0, 0.5))
        self.multi_toolbar_id = self.gui.addScrolledToolbar(self.gui.TopRight, 192, (192, 6000), x_offset=-192,
                                                            y_offset=128, hover_command=self.onToolbarHover,
                                                            color=(0, 0, 0, 0.5))
        self.wall_toolbar_id = self.gui.addScrolledToolbar(self.gui.TopRight, 192, (192, 6000), x_offset=-192,
                                                           y_offset=128, hover_command=self.onToolbarHover,
                                                           color=(0, 0, 0, 0.5))
        self.actor_toolbar_id = self.gui.addScrolledToolbar(self.gui.TopRight, 192, (192, 6000), x_offset=-192,
                                                            y_offset=128, hover_command=self.onToolbarHover,
                                                            color=(0, 0, 0, 0.5))
        self.collision_toolbar_id = self.gui.addScrolledToolbar(self.gui.TopRight, 192, (192, 6000), x_offset=-192,
                                                                y_offset=128, hover_command=self.onToolbarHover,
                                                                color=(0, 0, 0, 0.5))

        # get models
        dirList = listdir(Filename(path + cfg['model_dir']).toOsSpecific())
        for fname in dirList:
            if Filename(fname).getExtension() in ('egg', 'bam', 'pz'):
                model_name = Filename(fname).getBasenameWoExtension()
                if model_name[-4:] == '.egg':
                    model_name = model_name[:-4]
                self.gui.addListButton(self.object_toolbar_id, model_name, command=self.setObject,
                                       arg=[cfg['model_dir'] + model_name])
            elif isdir(path + cfg['model_dir'] + fname):
                self.gui.addListButton(self.multi_toolbar_id, fname, command=self.setNextObject,
                                       arg=[cfg['model_dir'] + fname + "/"])
        # get walls
        dirList = listdir(Filename(path + cfg['walls_dir']).toOsSpecific())
        for fname in dirList:
            if isdir(path + cfg['walls_dir'] + fname):
                self.gui.addListButton(self.wall_toolbar_id, fname, command=self.setNextObject,
                                       arg=[cfg['walls_dir'] + fname + "/"])
        # get actors
        dirList = listdir(Filename(path + cfg['actors_dir']).toOsSpecific())
        for fname in dirList:
            if isdir(path + cfg['actors_dir'] + fname):
                self.gui.addListButton(self.actor_toolbar_id, fname, command=self.setActor,
                                       arg=[cfg['actors_dir'] + fname])
        # get collision-models
        # these hava a part named 'editor', when loading these 'editor' parts should be hidden
        # appart from that collision-models are just like normal models
        dirList = listdir(Filename(path + cfg['coll_dir']).toOsSpecific())
        for fname in dirList:
            if Filename(fname).getExtension() in ('egg', 'bam', 'pz'):
                model_name = Filename(fname).getBasenameWoExtension()
                if model_name[-4:] == '.egg':
                    model_name = model_name[:-4]
                self.gui.addListButton(self.collision_toolbar_id, model_name, command=self.setObject,
                                       arg=[cfg['coll_dir'] + model_name])
        # object-mode toolbar
        self.mode_toolbar_id = self.gui.addToolbar(self.gui.TopRight, (192, 64), icon_size=64, x_offset=-192,
                                                   y_offset=0, hover_command=self.onToolbarHover)
        self.gui.addButton(self.mode_toolbar_id, cfg['theme'] + '/icon_object.png', self.setObjectMode,
                           [OBJECT_MODE_ONE], tooltip=self.tooltip, tooltip_text='Place single objects')
        self.gui.addButton(self.mode_toolbar_id, cfg['theme'] + '/icon_multi.png', self.setObjectMode,
                           [OBJECT_MODE_MULTI], tooltip=self.tooltip, tooltip_text='Place multiple, similar objects')
        self.gui.addButton(self.mode_toolbar_id, cfg['theme'] + '/icon_wall.png', self.setObjectMode,
                           [OBJECT_MODE_WALL], tooltip=self.tooltip, tooltip_text='Place walls')
        self.gui.addButton(self.mode_toolbar_id, cfg['theme'] + '/icon_pointer.png', self.setObjectMode,
                           [OBJECT_MODE_SELECT], tooltip=self.tooltip, tooltip_text='Pickup placed objects')
        self.gui.addButton(self.mode_toolbar_id, cfg['theme'] + '/icon_actor.png', self.setObjectMode,
                           [OBJECT_MODE_ACTOR], tooltip=self.tooltip,
                           tooltip_text='Place actors (models with animations)')
        self.gui.addButton(self.mode_toolbar_id, cfg['theme'] + '/icon_collision.png', self.setObjectMode,
                           [OBJECT_MODE_COLLISION], tooltip=self.tooltip,
                           tooltip_text='Place Collision solids, lights and particles')
        self.gui.grayOutButtons(self.mode_toolbar_id, (0, 6), 0)
        # object-mode select toolbar
        self.select_toolbar_id = self.gui.addToolbar(self.gui.TopRight, (192, 384), icon_size=32, x_offset=-192,
                                                     y_offset=128, hover_command=self.onToolbarHover,
                                                     color=(0, 0, 0, 0.5))
        # hack to add text
        self.gui.elements[self.select_toolbar_id]['frame']['text'] = "X:\nY:\nZ:\nH:\nP:\nR:\n      Scale:"
        self.gui.elements[self.select_toolbar_id]['frame']['text_scale'] = 32
        self.gui.elements[self.select_toolbar_id]['frame']['text_fg'] = (1, 1, 1, 1)
        self.gui.elements[self.select_toolbar_id]['frame']['text_font'] = self.gui.fontBig
        self.gui.elements[self.select_toolbar_id]['frame']['text_pos'] = (16, -24)
        for i in range(6):
            self.gui.addEntry(self.select_toolbar_id, size_x=180, offset_x=30)
        self.gui.addEntry(self.select_toolbar_id, size_x=125, offset_x=85)
        self.gui.addFloatingButton(self.select_toolbar_id, [128, 32], cfg['theme'] + '/apply.png', [32, 264],
                                   self.applyTransform, [0], tooltip=self.tooltip,
                                   tooltip_text='Apply changes in position, rotation and scale')
        self.gui.addFloatingButton(self.select_toolbar_id, [128, 32], cfg['theme'] + '/pickup.png', [32, 304],
                                   self.pickUp, [0], tooltip=self.tooltip,
                                   tooltip_text='Pick up the selected object and move it manualy')
        self.gui.addFloatingButton(self.select_toolbar_id, [128, 32], cfg['theme'] + '/delete.png', [32, 344],
                                   self.deleteObject, [0], tooltip=self.tooltip,
                                   tooltip_text='Delete the selected object')
        # color button
        self.gui.addColorPicker(apply_command=self.setLightColor)
        self.color_toolbar = self.gui.addToolbar(self.gui.TopLeft, (64, 64), icon_size=64,
                                                 hover_command=self.onToolbarHover, color=(1, 1, 1, 0.0))
        self.gui.addButton(self.color_toolbar, cfg['theme'] + '/icon_rgb.png', self.gui.showColorPicker, [],
                           tooltip=self.tooltip, tooltip_text='Set Light Color')

        # extra buttons for height paint mode (up/down/level)
        self.heightmode_toolbar_id = self.gui.addToolbar(self.gui.BottomRight, (256, 32), icon_size=64, y_offset=-64,
                                                         x_offset=-256, hover_command=self.onToolbarHover,
                                                         color=(1, 1, 1, 0.0))
        self.gui.addButton(self.heightmode_toolbar_id, cfg['theme'] + '/up.png', self.changeHeightMode,
                           [HEIGHT_MODE_UP], tooltip=self.tooltip,
                           tooltip_text='Raise terrain mode (click to set mode)')
        self.gui.addButton(self.heightmode_toolbar_id, cfg['theme'] + '/down.png', self.changeHeightMode,
                           [HEIGHT_MODE_DOWN], tooltip=self.tooltip,
                           tooltip_text='Lower terrain mode (click to set mode)')
        self.gui.addButton(self.heightmode_toolbar_id, cfg['theme'] + '/level.png', self.changeHeightMode,
                           [HEIGHT_MODE_LEVEL], tooltip=self.tooltip,
                           tooltip_text='Level terrain mode (click to set mode)')
        self.gui.addButton(self.heightmode_toolbar_id, cfg['theme'] + '/blur.png', self.changeHeightMode,
                           [HEIGHT_MODE_BLUR], tooltip=self.tooltip,
                           tooltip_text='Smooth terrain mode (click to set mode)')
        self.gui.grayOutButtons(self.heightmode_toolbar_id, (0, 4), 0)

        # extra buttons for walkmap paint (walkable/unwealkable)
        self.walkmap_toolbar_id = self.gui.addToolbar(self.gui.BottomRight, (128, 64), icon_size=64, y_offset=-64,
                                                      x_offset=-128, hover_command=self.onToolbarHover,
                                                      color=(1, 1, 1, 0.3))
        self.gui.addButton(self.walkmap_toolbar_id, cfg['theme'] + '/icon_nowalk.png', self.changeWalkMode,
                           [WALK_MODE_NOWALK], tooltip=self.tooltip, tooltip_text='Paint un-walkable area(marked RED)')
        self.gui.addButton(self.walkmap_toolbar_id, cfg['theme'] + '/icon_walk.png', self.changeWalkMode,
                           [WALK_MODE_WALK], tooltip=self.tooltip, tooltip_text='Paint walkable area')
        self.gui.grayOutButtons(self.walkmap_toolbar_id, (0, 2), 0)

        # extra buttons for grass paint (add/remove) self.grass_toolbar_id=self.gui.addToolbar(self.gui.BottomRight,
        # (128, 64), icon_size=64, y_offset=-64,x_offset=-128, hover_command=self.onToolbarHover, color=(1,1,1,
        # 0.3)) self.gui.addButton(self.grass_toolbar_id, cfg['theme']+'/no_grass.png', self.changeGrassMode,
        # [GRASS_MODE_REMOVE],tooltip=self.tooltip, tooltip_text='Remove grass') self.gui.addButton(
        # self.grass_toolbar_id, cfg['theme']+'/grass.png', self.changeGrassMode,[GRASS_MODE_PAINT],
        # tooltip=self.tooltip, tooltip_text='Paint grass') self.gui.grayOutButtons(self.grass_toolbar_id, (0,2),
        # 1) self.painter.brushes[BUFFER_GRASS].setColor(1,0,0,1)

        # properties panel
        self.prop_panel_id = self.gui.addPropPanel()
        self.props = self.gui.elements[self.prop_panel_id]['entry_props']
        self.snap = self.gui.elements[self.prop_panel_id]['entry_snap']

    def init_mesh(self):
        self.mesh = loader.loadModel(cfg['terrain_mesh'])
        # load default textures: TODO(maybe): remove default tex from model ... and fix filtering then somehow for
        #  tex in self.textures_diffuse[:6]: id=self.textures_diffuse.index(tex) self.mesh.setTexture(
        #  self.mesh.findTextureStage('tex{0}'.format(id+1)), loader.loadTexture(tex, anisotropicDegree=2 ),
        #  1) for tex in self.textures_normal[:6]: id=self.textures_normal.index(tex) self.mesh.setTexture(
        #  self.mesh.findTextureStage('tex{0}n'.format(id+1)), loader.loadTexture(tex, anisotropicDegree=2), 1)

        # srgb=ConfigVariableBool('framebuffer-srgb',False).getValue()
        srgb = cfg["srgb"]
        # print srgb

        for tex in self.textures_diffuse[:6]:
            id = self.textures_diffuse.index(tex)
            new_tex = loader.loadTexture(tex, anisotropicDegree=2)
            # if ConfigVariableBool('framebuffer-srgb',False).getValue():
            if cfg["srgb"]:
                tex_format = new_tex.getFormat()
                if tex_format == Texture.F_rgb:
                    tex_format = Texture.F_srgb
                elif tex_format == Texture.F_rgba:
                    tex_format = Texture.F_srgb_alpha
                new_tex.setFormat(tex_format)
            self.mesh.setTexture(self.mesh.findTextureStage('tex{0}'.format(id + 1)), new_tex, 1)

        for tex in self.textures_normal[:6]:
            id = self.textures_normal.index(tex)
            self.mesh.setTexture(self.mesh.findTextureStage('tex{0}n'.format(id + 1)),
                                 loader.loadTexture(tex, anisotropicDegree=2), 1)

        self.mesh.reparentTo(render)

        if cfg["shader_terrain_tes"] == '':
            self.mesh.setShader(Shader.load(Shader.SLGLSL, cfg["shader_terrain_v"], cfg["shader_terrain_f"]))
        else:
            convertToPatches(self.mesh)
            self.mesh.setShader(Shader.load(Shader.SLGLSL, cfg["shader_terrain_v"], cfg["shader_terrain_f"], "",
                                            cfg["shader_terrain_tc"], cfg["shader_terrain_tes"]))

        self.mesh.setShaderInput("height", self.painter.textures[BUFFER_HEIGHT])
        self.mesh.setShaderInput("atr1", self.painter.textures[BUFFER_ATR])
        self.mesh.setShaderInput("atr2", self.painter.textures[BUFFER_ATR2])
        self.mesh.setShaderInput("walkmap", self.painter.textures[BUFFER_WALK])
        render.setShaderInput("z_scale", 100.0)
        self.mesh.setShaderInput("tex_scale", 16.0)
        self.mesh.setTransparency(TransparencyAttrib.MNone, 1)
        self.mesh.node().setBounds(OmniBoundingVolume())
        self.mesh.node().setFinal(1)
        self.mesh.setBin("background", 11)
        self.mesh.showThrough(MASK_TERRAIN_ONLY)
        if cfg['shadow_terrain'] == False:
            self.mesh.hide(MASK_SHADOW)
        if cfg['reflect_terrain'] == False:
            self.mesh.hide(MASK_WATER)

    def init_grass(self):
        self.grass = render.attachNewNode('grass')
        self.CreateGrassTile(uv_offset=Vec2(0, 0), pos=(0, 0, 0), parent=self.grass, fogcenter=Vec3(256, 256, 0))
        self.CreateGrassTile(uv_offset=Vec2(0, 0.5), pos=(0, 256, 0), parent=self.grass, fogcenter=Vec3(256, 0, 0))
        self.CreateGrassTile(uv_offset=Vec2(0.5, 0), pos=(256, 0, 0), parent=self.grass, fogcenter=Vec3(0, 256, 0))
        self.CreateGrassTile(uv_offset=Vec2(0.5, 0.5), pos=(256, 256, 0), parent=self.grass, fogcenter=Vec3(0, 0, 0))
        self.grass.setBin("background", 11)
        if cfg['reflect_grass'] == False:
            self.grass.hide(MASK_WATER)
        if cfg['shadow_grass'] == False:
            self.grass.hide(MASK_SHADOW)

        grass_tex0 = loader.loadTexture('grass/1.png')
        grass_tex0.setWrapU(Texture.WMClamp)
        grass_tex0.setWrapV(Texture.WMClamp)
        grass_tex0.setMinfilter(Texture.FTLinearMipmapLinear)
        grass_tex0.setMagfilter(Texture.FTLinear)

        grass_tex1 = loader.loadTexture('grass/2.png')
        grass_tex1.setWrapU(Texture.WMClamp)
        grass_tex1.setWrapV(Texture.WMClamp)
        grass_tex1.setMinfilter(Texture.FTLinearMipmapLinear)
        grass_tex1.setMagfilter(Texture.FTLinear)

        grass_tex2 = loader.loadTexture('grass/3.png')
        grass_tex2.setWrapU(Texture.WMClamp)
        grass_tex2.setWrapV(Texture.WMClamp)
        grass_tex2.setMinfilter(Texture.FTLinearMipmapLinear)
        grass_tex2.setMagfilter(Texture.FTLinear)

        self.grass.setTexture(self.grass.findTextureStage('tex1'), grass_tex0, 1)
        self.grass.setTexture(self.grass.findTextureStage('tex2'), grass_tex1, 1)
        self.grass.setTexture(self.grass.findTextureStage('tex3'), grass_tex2, 1)
        if cfg['grass'] == False:
            self.grass.hide()

    def init_sky(self):
        self.skydome = loader.loadModel(cfg['sky_mesh'])
        self.skydome.reparentTo(render)
        self.skydome.setPos(256, 256, -200)
        self.skydome.setScale(10)
        self.skydome.setShaderInput("sky", Vec4(0.4, 0.6, 1.0, 1.0))
        # self.skydome.setShaderInput("fog", Vec4(1.0,1.0,1.0, 1.0))
        self.skydome.setShaderInput("cloudColor", Vec4(0.9, 0.9, 1.0, 0.8))
        self.skydome.setShaderInput("cloudTile", 8.0)
        self.skydome.setShaderInput("cloudSpeed", 0.008)
        self.skydome.setShaderInput("horizont", 20.0)
        self.skydome.setShaderInput("sunColor", Vec4(1.0, 1.0, 1.0, 1.0))
        self.skydome.setShaderInput("skyColor", Vec4(1.0, 1.0, 1.0, 1.0))
        self.skydome.setBin('background', 1)
        self.skydome.setTwoSided(True)
        self.skydome.node().setBounds(OmniBoundingVolume())
        self.skydome.node().setFinal(1)
        self.skydome.setShader(Shader.load(Shader.SLGLSL, cfg["shader_sky_v"], cfg["shader_sky_f"]))
        self.skydome.hide(MASK_SHADOW)
        self.skydome.setTransparency(TransparencyAttrib.MNone, 1)
        if cfg['reflect_sky'] == False:
            self.skydome.hide(MASK_WATER)

    def init_water(self):
        self.waterNP = loader.loadModel(cfg['water_mesh'])
        self.waterNP.setPos(256, 256, 0)
        self.waterNP.setTransparency(TransparencyAttrib.MAlpha)
        self.waterNP.flattenLight()
        self.waterNP.setPos(0, 0, 30)
        self.waterNP.reparentTo(render)
        # Add a buffer and camera that will render the reflection texture
        self.wBuffer = base.win.makeTextureBuffer("water", 512, 512)
        # self.wBuffer.setClearColorActive(True)
        self.wBuffer.setClearColor(base.win.getClearColor())
        self.wBuffer.setSort(-1)
        self.waterCamera = base.makeCamera(self.wBuffer)
        self.waterCamera.reparentTo(render)
        self.waterCamera.node().setLens(base.camLens)
        self.waterCamera.node().setCameraMask(MASK_WATER)
        # Create this texture and apply settings
        wTexture = self.wBuffer.getTexture()
        wTexture.setWrapU(Texture.WMClamp)
        wTexture.setWrapV(Texture.WMClamp)
        # wTexture.setMinfilter(Texture.FTLinearMipmapLinear)
        # Create plane for clipping and for reflection matrix
        self.wPlane = Plane(Vec3(0, 0, 1), Point3(0, 0, 30))
        wPlaneNP = render.attachNewNode(PlaneNode("water", self.wPlane))
        tmpNP = NodePath("StateInitializer")
        tmpNP.setClipPlane(wPlaneNP)
        tmpNP.setAttrib(CullFaceAttrib.makeReverse())
        self.waterCamera.node().setInitialState(tmpNP.getState())
        # self.waterCamera.node().showFrustum()
        # self.waterNP.projectTexture(TextureStage("reflection"), wTexture, self.waterCamera)
        # reflect UV generated on the shader - faster(?)
        self.waterNP.setShaderInput('camera', self.waterCamera)
        self.waterNP.setShaderInput("reflection", wTexture)

        self.waterNP.setShader(Shader.load(Shader.SLGLSL, cfg["shader_water_v"], cfg["shader_water_f"]))
        self.waterNP.setShaderInput("water_norm", loader.loadTexture(cfg['water_tex']))
        self.waterNP.setShaderInput("water_height", loader.loadTexture(cfg['wave_tex']))
        self.waterNP.setShaderInput("height", self.painter.textures[BUFFER_HEIGHT])
        self.waterNP.setShaderInput("tile", 20.0)
        self.waterNP.setShaderInput("water_level", 30.0)
        self.waterNP.setShaderInput("speed", 0.01)
        self.waterNP.setShaderInput("wave", Vec4(0.005, 0.002, 6.0, 1.0))
        self.waterNP.hide(MASK_WATER)
        # self.waterNP.hide(MASK_SHADOW)
        # hide water by default
        self.waterNP.hide()
        # self.waterNP.setDepthWrite(False)
        self.waterNP.setBin("transparent", 31)
        self.wBuffer.setActive(False)
        self.mesh.setShaderInput("water_level", -1.0)

    def init_light(self):
        self.sun = self.light_manager.addLight(pos=(256.0, 256.0, 200.0), color=(0.9, 0.9, 0.9), radius=10000.0)
        render.setShaderInput('daytime', 12.0)

        # ambient light
        self.light_manager.ambientLight(0.15, 0.15, 0.2)

        self.shadowCamera = render.attachNewNode('fake_shadow_camera_node')
        self.shadowCamera.setPos(256, 256, 1000)
        self.shadowCamera.setHpr(90, -90, 0)
        self.sunNode = render.attachNewNode('sunNode')
        self.sunNode.setPos(256, 256, 0)
        self.shadowCamera.wrtReparentTo(self.sunNode)

    def set_keys(self):
        self.keyMap = {'paint': False,
                       'rotate_l': False,
                       'rotate_r': False,
                       'alpha_up': False,
                       'alpha_down': False,
                       'scale_up': False,
                       'scale_down': False}

        self.accept(cfg['key_paint'], self.keyMap.__setitem__, ['paint', True])
        self.accept(cfg['key_paint'] + '-up', self.keyMap.__setitem__, ['paint', False])
        self.accept(cfg['key_right'], self.keyMap.__setitem__, ['rotate_r', True])
        self.accept(cfg['key_right'] + '-up', self.keyMap.__setitem__, ['rotate_r', False])
        self.accept(cfg['key_left'], self.keyMap.__setitem__, ['rotate_l', True])
        self.accept(cfg['key_left'] + '-up', self.keyMap.__setitem__, ['rotate_l', False])
        self.accept(cfg['key_scale_up'], self.keyMap.__setitem__, ['scale_up', True])
        self.accept(cfg['key_scale_up'] + '-up', self.keyMap.__setitem__, ['scale_up', False])
        self.accept(cfg['key_scale_down'], self.keyMap.__setitem__, ['scale_down', True])
        self.accept(cfg['key_scale_down'] + '-up', self.keyMap.__setitem__, ['scale_down', False])
        self.accept(cfg['key_alpha_up'], self.keyMap.__setitem__, ['alpha_up', True])
        self.accept(cfg['key_alpha_up'] + '-up', self.keyMap.__setitem__, ['alpha_up', False])
        self.accept(cfg['key_alpha_down'], self.keyMap.__setitem__, ['alpha_down', True])
        self.accept(cfg['key_alpha_down'] + '-up', self.keyMap.__setitem__, ['alpha_down', False])
        self.accept(cfg['key_next'], self.nextModel)
        self.accept(cfg['key_prev'], self.previousModel)
        self.accept(cfg['key_mode_height'], self.setMode, [MODE_HEIGHT, 'hotkey'])
        self.accept(cfg['key_mode_tex'], self.setMode, [MODE_TEXTURE, 'hotkey'])
        self.accept(cfg['key_mode_grass'], self.setMode, [MODE_GRASS, 'hotkey'])
        self.accept(cfg['key_mode_obj'], self.setMode, [MODE_OBJECT, 'hotkey'])
        self.accept(cfg['key_mode_walk'], self.setMode, [MODE_WALK, 'hotkey'])
        self.accept(cfg['key_config'], self.configSkySea, [True])
        self.accept(cfg['key_save'], self.showSaveMenu)
        self.accept(cfg['key_h'], self.setAxis, ['H: '])
        self.accept(cfg['key_p'], self.setAxis, ['P: '])
        self.accept(cfg['key_r'], self.setAxis, ['R: '])
        self.accept('escape', self.objectPainter.stop)
        self.accept('enter', self.focusOnProperties)
        self.accept('window-event', self.windowEventHandler)

    def set_init_values(self):
        self.setMode(MODE_HEIGHT)
        self.setBrush(0)
        self.painter.setBrushIDColor(BUFFER_ATR, (0, 0, 0, 1.0))
        self.painter.setBrushIDColor(BUFFER_ATR2, (0, 0, 1, 1.0))
        self.setTime(12.0)

    # -------------- End Of Initializing ------------------

    def setHeading(self, slider):
        if self.mode in (MODE_GRASS, MODE_HEIGHT, MODE_TEXTURE, MODE_WALK):
            self.painter.setBrushHeading(slider)
            self.heading_info['text'] = self.hpr_axis + '%.0f' % self.painter.brushes[0].getH()
        else:
            self.heading_info['text'] = self.objectPainter.setHpr(self.hpr_axis, slider=slider)

    def setStrength(self, slider):
        if self.mode in (MODE_GRASS, MODE_HEIGHT, MODE_TEXTURE, MODE_WALK):
            self.painter.setBrushAlpha(slider)
            self.color_info['text'] = '%.2f' % self.painter.brushAlpha
        else:
            self.objectPainter.setZ(slider)
            self.color_info['text'] = '%.2f' % self.objectPainter.currentZ

    def setSize(self, slider):
        if self.mode in (MODE_GRASS, MODE_HEIGHT, MODE_TEXTURE, MODE_WALK):
            self.painter.setBrushSize(slider)
            self.size_info['text'] = '%.2f' % self.painter.brushSize
        else:
            self.objectPainter.setScale(slider)
            self.size_info['text'] = '%.2f' % self.objectPainter.currentScale

    def setLightColor(self):
        if self.objectPainter.currentObject:
            if self.objectPainter.currentObject.hasPythonTag('hasLight'):
                id = self.objectPainter.currentObject.getPythonTag('hasLight')
                rgb = self.gui.sample['frameColor']
                self.light_manager.setColor(id, rgb)
                self.objectPainter.currentObject.setPythonTag('light_color', [rgb[0], rgb[1], rgb[2]])
        elif self.objectPainter.selectedObject:
            if self.objectPainter.selectedObject.hasPythonTag('hasLight'):
                id = self.objectPainter.selectedObject.getPythonTag('hasLight')
                rgb = self.gui.sample['frameColor']
                self.light_manager.setColor(id, rgb)
                self.objectPainter.selectedObject.setPythonTag('light_color', [rgb[0], rgb[1], rgb[2]])

    def clockTick(self, task):
        self.clock += 0.02
        if self.clock > 23.9:
            self.clock = 0.0
        self.setTime(self.clock)
        return task.again

    def blendPixels(self, p1, p2, blend):
        c1 = [p1[0] / 255.0, p1[1] / 255.0, p1[2] / 255.0, p1[3] / 255.0]
        c2 = [p2[0] / 255.0, p2[1] / 255.0, p2[2] / 255.0, p2[3] / 255.0]
        return Vec4(c1[0] * blend + c2[0] * (1.0 - blend), c1[1] * blend + c2[1] * (1.0 - blend),
                    c1[2] * blend + c2[2] * (1.0 - blend), c1[3] * blend + c2[3] * (1.0 - blend))

    def setTime(self, time, event=None, fog_co=1.0):
        sunpos = min(0.5, max(-0.5, (time - 12.0) / 14.0))
        render.setShaderInput('sunpos', sunpos)
        x1 = int(time)
        x2 = x1 - 1
        if x2 < 0:
            x2 = 0
        blend = time % 1.0

        p1 = self.skyimg.getPixel(x1, 0)
        p2 = self.skyimg.getPixel(x2, 0)
        sunColor = self.blendPixels(p1, p2, blend)
        sunColor[0] = sunColor[0] * 1.3
        sunColor[1] = sunColor[1] * 1.3
        sunColor[2] = sunColor[2] * 1.3
        p1 = self.skyimg.getPixel(x1, 1)
        p2 = self.skyimg.getPixel(x2, 1)
        skyColor = self.blendPixels(p1, p2, blend)

        p1 = self.skyimg.getPixel(x1, 2)
        p2 = self.skyimg.getPixel(x2, 2)
        cloudColor = self.blendPixels(p1, p2, blend)

        p1 = self.skyimg.getPixel(x1, 3)
        p2 = self.skyimg.getPixel(x2, 3)
        fogColor = self.blendPixels(p1, p2, blend)
        fogColor[3] = (abs(sunpos) * 0.008 + 0.001) * fog_co

        if time < 6.0 or time > 18.0:
            p = 0.0
        else:
            p = sunpos * -180.0

        self.sunNode.setP(p)
        self.light_manager.moveLight(self.sun, self.shadowCamera.getPos(render))
        self.light_manager.setLight(id=self.sun, pos=self.shadowCamera.getPos(render), color=sunColor, radius=10000.0)
        self.skydome.setShaderInput("sunColor", sunColor)
        self.skydome.setShaderInput("skyColor", skyColor)
        self.skydome.setShaderInput("cloudColor", cloudColor)
        render.setShaderInput("fog", fogColor)

    def findLights(self):
        for node in self.objectPainter.quadtree:
            for child in node.getChildren():
                if child.hasPythonTag('hasLight'):
                    pos = child.getPos(render)
                    color = child.getPythonTag('light_color')
                    radi = child.getScale()[0] * 10.0
                    id = self.light_manager.addLight(pos, color, radi)
                    child.setPythonTag('hasLight', id)

    def setupFilters(self, manager, path="", fxaa_only=False):
        colorTex = Texture()  # the scene
        filters = []
        final_quad = manager.renderSceneInto(colortex=colorTex)
        # fxaa
        final_quad.setShader(Shader.load(Shader.SLGLSL, path + "shaders/fxaa_v.glsl", path + "shaders/fxaa_f.glsl"))
        final_quad.setShaderInput("tex0", colorTex)
        final_quad.setShaderInput("rt_w", float(base.win.getXSize()))
        final_quad.setShaderInput("rt_h", float(base.win.getYSize()))
        final_quad.setShaderInput("FXAA_SPAN_MAX", float(8.0))
        final_quad.setShaderInput("FXAA_REDUCE_MUL", float(1.0 / 8.0))
        final_quad.setShaderInput("FXAA_SUBPIX_SHIFT", float(1.0 / 4.0))
        filters.append(final_quad)
        return filters

    def deleteObject(self, not_used=None, guiEvent=None):
        node = self.objectPainter.selectedObject
        if node:
            if node.hasPythonTag('hasLight'):
                l = node.getPythonTag('hasLight')
                self.light_manager.removeLight(l)
            if node in self.objectPainter.actors:
                self.objectPainter.actors.pop(self.objectPainter.actors.index(node)).cleanup()
            node.removeNode()
            self.objectPainter.selectedObject = None
            self.setObjectMode(OBJECT_MODE_ONE)
            self.props.set('')

    def applyTransform(self, not_used=None, guiEvent=None):
        x = self.gui.elements[self.select_toolbar_id]['buttons'][0].get()
        y = self.gui.elements[self.select_toolbar_id]['buttons'][1].get()
        z = self.gui.elements[self.select_toolbar_id]['buttons'][2].get()
        h = self.gui.elements[self.select_toolbar_id]['buttons'][3].get()
        p = self.gui.elements[self.select_toolbar_id]['buttons'][4].get()
        r = self.gui.elements[self.select_toolbar_id]['buttons'][5].get()
        scale = self.gui.elements[self.select_toolbar_id]['buttons'][6].get()
        x = self.objectPainter._stringToFloat(x)
        y = self.objectPainter._stringToFloat(y)
        z = self.objectPainter._stringToFloat(z)
        h = self.objectPainter._stringToFloat(h)
        p = self.objectPainter._stringToFloat(p)
        r = self.objectPainter._stringToFloat(r)
        scale = self.objectPainter._stringToFloat(scale)
        rgb = self.gui.sample['frameColor']
        self.objectPainter.selectedObject.setPosHpr((x, y, z), (h, p, r))
        self.objectPainter.selectedObject.setScale(scale)
        if self.objectPainter.selectedObject.hasPythonTag('hasLight'):
            id = self.objectPainter.selectedObject.getPythonTag('hasLight')
            self.light_manager.setLight(id, self.objectPainter.selectedObject.getPos(render), rgb, 10.0 * scale)
            self.objectPainter.selectedObject.setPythonTag('light_color', [rgb[0], rgb[1], rgb[2]])
            self.gui.colorPickerFrame.hide()
        self.gui.elements[self.select_toolbar_id]['buttons'][0]['focus'] = 0
        self.gui.elements[self.select_toolbar_id]['buttons'][1]['focus'] = 0
        self.gui.elements[self.select_toolbar_id]['buttons'][2]['focus'] = 0
        self.gui.elements[self.select_toolbar_id]['buttons'][3]['focus'] = 0
        self.gui.elements[self.select_toolbar_id]['buttons'][4]['focus'] = 0
        self.gui.elements[self.select_toolbar_id]['buttons'][5]['focus'] = 0
        self.gui.elements[self.select_toolbar_id]['buttons'][6]['focus'] = 0

        props = self.props.get()
        self.objectPainter.selectedObject.setPythonTag('props', props)
        self.props.set('')
        self.props['focus'] = 0
        self.gui.hideElement(self.select_toolbar_id)
        self.setObjectMode(OBJECT_MODE_SELECT)

    def pickUp(self, not_used=None, guiEvent=None):
        h = self.gui.elements[self.select_toolbar_id]['buttons'][3].get()
        p = self.gui.elements[self.select_toolbar_id]['buttons'][4].get()
        r = self.gui.elements[self.select_toolbar_id]['buttons'][5].get()
        h = self.objectPainter._stringToFloat(h)
        p = self.objectPainter._stringToFloat(p)
        r = self.objectPainter._stringToFloat(r)
        self.objectPainter.currentHPR = [h, p, r]
        self.objectPainter.pickup()
        self.setObjectMode(OBJECT_MODE_ONE)
        self.heading_info['text'] = self.objectPainter.adjustHpr(0, self.hpr_axis)
        self.size_info['text'] = '%.2f' % self.objectPainter.currentScale
        self.color_info['text'] = '%.2f' % self.objectPainter.currentZ
        self.props.set(self.objectPainter.currentObject.getPythonTag('props'))

    def configSkySea(self, options=False, guiEvent=None):
        print(options, guiEvent)
        if options == True:
            self.ignoreHover = True
            self.painter.hideBrushes()
            self.gui.SkySeaFrame.show()
            self.ignore('mouse1-up')
            self.ignore('mouse1')

        elif options == False:
            self.ignoreHover = False
            self.gui.SkySeaFrame.hide()
            self.setMode(self.mode)

        else:
            self.ignoreHover = False
            self.gui.SkySeaFrame.hide()
            self.setMode(self.mode)

            TerrainTile = self.gui.SkySeaOptions[0]
            TerrainScale = self.gui.SkySeaOptions[1]
            SkyTile = self.gui.SkySeaOptions[2]
            CloudSpeed = self.gui.SkySeaOptions[3]
            WaveTile = self.gui.SkySeaOptions[4]
            WaveHeight = self.gui.SkySeaOptions[5]
            WaveXYMove = [self.gui.SkySeaOptions[6][0], self.gui.SkySeaOptions[6][1]]
            WaterTile = self.gui.SkySeaOptions[7]
            WaterSpeed = self.gui.SkySeaOptions[8]
            WaterLevel = self.gui.SkySeaOptions[9]

            self.skydome.setShaderInput("cloudTile", SkyTile)
            self.skydome.setShaderInput("cloudSpeed", CloudSpeed)
            self.mesh.setShaderInput("water_level", WaterLevel)
            # self.mesh.setShaderInput("z_scale", TerrainScale)
            render.setShaderInput("z_scale", TerrainScale)
            self.mesh.setShaderInput("tex_scale", TerrainTile)
            if cfg['use_gl_select']:
                self.painter.setup_gl_select(self.painter.textures[BUFFER_HEIGHT], TerrainScale)
            if WaterLevel > 0.0:
                self.wBuffer.setActive(True)
                self.waterNP.show()
                self.waterNP.setShaderInput("tile", WaterTile)
                self.waterNP.setShaderInput("speed", WaterSpeed)
                self.waterNP.setShaderInput("water_level", WaterLevel)
                self.waterNP.setShaderInput("wave", Vec4(WaveXYMove[0], WaveXYMove[1], WaveTile, WaveHeight))
                self.waterNP.setPos(0, 0, WaterLevel)
                self.wPlane = Plane(Vec3(0, 0, 1), Point3(0, 0, WaterLevel))
                wPlaneNP = render.attachNewNode(PlaneNode("water", self.wPlane))
                self.mesh.setShaderInput("water_level", WaterLevel)
                tmpNP = NodePath("StateInitializer")
                tmpNP.setClipPlane(wPlaneNP)
                tmpNP.setAttrib(CullFaceAttrib.makeReverse())
                self.waterCamera.node().setInitialState(tmpNP.getState())
            else:
                self.waterNP.hide()
                self.wBuffer.setActive(False)
                self.mesh.setShaderInput("water_level", -10.0)

    def configBrush(self, options=False, guiEvent=None):
        if options == True:
            self.ignoreHover = True
            self.painter.hideBrushes()
            self.gui.ConfigFrame.show()
            self.ignore('mouse1-up')
            self.ignore('mouse1')
            self.gui.ConfigEntry[0].enterText(self.size_info['text'])
            self.gui.ConfigEntry[1].enterText(self.color_info['text'])
            if self.mode == MODE_OBJECT:
                self.gui.ConfigEntry[2].enterText(str(self.objectPainter.currentHPR[0]))
                self.gui.ConfigEntry[3].enterText(str(self.objectPainter.currentHPR[1]))
                self.gui.ConfigEntry[4].enterText(str(self.objectPainter.currentHPR[2]))
            else:
                self.gui.ConfigEntry[2].enterText(str(self.painter.brushes[0].getH()))
                self.gui.ConfigEntry[3].enterText('0.0')
                self.gui.ConfigEntry[4].enterText('0.0')
            self.gui.ConfigEntry[5].enterText(str(self.grid_scale))
            self.gui.ConfigEntry[6].enterText(str(self.grid_z))
        elif options == False:
            self.ignoreHover = False
            self.gui.ConfigFrame.hide()
            self.setMode(self.mode)
        else:
            self.ignoreHover = False
            self.gui.ConfigFrame.hide()
            self.setMode(self.mode)
            self.grid.setZ(self.gui.ConfigOptions[6])
            self.grid_scale = self.gui.ConfigOptions[5]
            self.grid_z = self.gui.ConfigOptions[6]
            if self.grid_scale > 0:
                self.grid.show()
                self.grid.setTexScale(TextureStage.getDefault(), self.gui.ConfigOptions[5], self.grid_scale, 1)
            else:
                self.grid.hide()
            self.painter.pointer.setZ(self.gui.ConfigOptions[6])
            self.painter.plane = Plane(Vec3(0, 0, 1), Point3(0, 0, self.gui.ConfigOptions[6]))
            self.controler.cameraNode.setZ(self.gui.ConfigOptions[6])
            daytime = float(self.gui.ConfigOptions[7])
            self.setTime(daytime, fog_co=float(self.gui.ConfigOptions[8]))
            # render.setShaderInput('daytime', daytime)
            # self.dlight.setColor(Vec4(color, color, color, 1))
            if self.mode == MODE_OBJECT:
                # hpr
                self.setAxis = 'H: '
                self.heading_info['text'] = self.setAxis + str(self.gui.ConfigOptions[2])
                self.objectPainter.currentHPR = [self.gui.ConfigOptions[2], self.gui.ConfigOptions[3],
                                                 self.gui.ConfigOptions[4]]
                # scale
                self.objectPainter.currentScale = self.gui.ConfigOptions[0]
                self.size_info['text'] = '%.2f' % self.objectPainter.currentScale
                # alpha (Z)
                self.objectPainter.currentZ = self.gui.ConfigOptions[1]
                self.color_info['text'] = '%.2f' % self.objectPainter.currentZ
            else:
                # hpr
                for brush in self.painter.brushes:
                    brush.setH(self.gui.ConfigOptions[2])
                self.heading_info['text'] = self.hpr_axis + '%.0f' % self.painter.brushes[0].getH()
                # scale
                self.painter.brushSize = self.gui.ConfigOptions[0]
                self.painter.adjustBrushSize(0)
                self.size_info['text'] = '%.2f' % self.painter.brushSize
                # alpha (color)
                if self.mode == MODE_HEIGHT and self.height_mode == HEIGHT_MODE_LEVEL:
                    self.tempColor = self.gui.ConfigOptions[1]
                    self.painter.setBrushIDColor(BUFFER_HEIGHT, (self.tempColor, self.tempColor, self.tempColor, 1))
                    self.color_info['text'] = '%.2f' % self.tempColor
                else:
                    self.painter.brushAlpha = self.gui.ConfigOptions[1]
                    self.painter.adjustBrushAlpha(0)
                    self.color_info['text'] = '%.2f' % self.painter.brushAlpha

    def changeGrassMode(self, mode=None, guiEvent=None):
        self.gui.grayOutButtons(self.grass_toolbar_id, (0, 2), mode)
        self.painter.setBrushIDColor(BUFFER_GRASS, (mode, 0, 0, 1))

    def changeWalkMode(self, mode=None, guiEvent=None):
        self.gui.grayOutButtons(self.walkmap_toolbar_id, (0, 2), mode)
        if mode == WALK_MODE_NOWALK:
            self.painter.setBrushIDColor(BUFFER_WALK, (1, 0, 0, 1.0))
        else:
            self.painter.setBrushIDColor(BUFFER_WALK, (0, 0, 0, 1.0))

    def changeHeightMode(self, mode=None, guiEvent=None):
        if mode == None:
            mode = self.height_mode + 1
        if mode > HEIGHT_MODE_BLUR:
            mode = HEIGHT_MODE_UP
        if mode == HEIGHT_MODE_UP:
            self.tempColor = 1
            self.painter.brushAlpha = 0.05
            self.painter.setBrushIDColor(BUFFER_HEIGHT, (1, 1, 1, 0.5), False)
            self.color_info['text'] = '%.2f' % 0.05
            self.painter.brushes[BUFFER_HEIGHT].setShaderInput('use_map', 0.0)
        if mode == HEIGHT_MODE_DOWN:
            self.tempColor = 0
            self.painter.brushAlpha = 0.05
            self.painter.setBrushIDColor(BUFFER_HEIGHT, (0, 0, 0, 0.05), False)
            self.color_info['text'] = '%.2f' % 0.05
            self.painter.brushes[BUFFER_HEIGHT].setShaderInput('use_map', 0.0)
        if mode == HEIGHT_MODE_LEVEL:
            self.tempColor = self.painter.brushAlpha
            self.tempAlpha = self.painter.brushAlpha
            self.painter.brushAlpha = 0.25
            self.painter.setBrushIDColor(BUFFER_HEIGHT, (self.tempColor, self.tempColor, self.tempColor, 0.25), False)
            self.color_info['text'] = '%.2f' % 0.25
            self.painter.brushes[BUFFER_HEIGHT].setShaderInput('use_map', 0.0)
        if mode == HEIGHT_MODE_BLUR:
            self.painter.brushes[BUFFER_HEIGHT].setShaderInput('use_map', 1.0)
            self.tempColor = self.painter.brushAlpha
            self.tempAlpha = self.painter.brushAlpha
            self.painter.brushAlpha = 1
            self.painter.setBrushIDColor(BUFFER_HEIGHT, (self.tempColor, self.tempColor, self.tempColor, 1), False)
            self.color_info['text'] = '%.2f' % self.tempColor
        self.gui.grayOutButtons(self.heightmode_toolbar_id, (0, 4), mode)
        self.height_mode = mode

    def focusOnProperties(self):
        self.props['focus'] = 1

    def setRandomWall(self, model_path=None, id=None, guiEvent=None):
        # if id!=None:
        #    self.gui.blink(self.multi_toolbar_id, id)
        if model_path == None:
            model_path = self.last_model_path
        models = []
        dirList = listdir(Filename(model_path).toOsSpecific())
        for fname in dirList:
            if Filename(fname).getExtension() in ('egg', 'bam', 'pz'):
                model_name = str(Filename(fname).getBasenameWoExtension()).strip(".egg")
                models.append(model_path + model_name)
        self.objectPainter.loadWall(random.choice(models))
        self.last_model_path = model_path

    def nextWall(self, model_path=None, direction=1):
        if model_path == None:
            model_path = self.last_model_path
        else:
            self.last_object_index = -1
        models = []
        dirList = listdir(Filename(model_path).toOsSpecific())
        for fname in dirList:
            if Filename(fname).getExtension() in ('egg', 'bam', 'pz'):
                model_name = str(Filename(fname).getBasenameWoExtension()).strip(".egg")
                models.append(model_path + model_name)
        if self.last_object_index + direction < len(models):
            self.last_object_index += direction
            if self.last_object_index < 0:
                self.last_object_index = len(models) - 1
        else:
            self.last_object_index = 0
        print("model index: ", self.last_object_index)

        if self.objectPainter.currentWall:
            self.objectPainter.loadWall(models[self.last_object_index], True)
        else:
            self.objectPainter.loadModel(models[self.last_object_index])
        self.last_model_path = model_path

    def setNextObject(self, model_path=None, direction=1, id=None, guiEvent=None):
        # if id!=None:
        #    self.gui.blink(self.multi_toolbar_id, id)
        if model_path == None:
            model_path = self.last_model_path
        else:
            self.last_object_index = -1
        models = []
        dirList = listdir(Filename(model_path).toOsSpecific())
        for fname in dirList:
            if Filename(fname).getExtension() in ('egg', 'bam', 'pz'):
                model_name = str(Filename(fname).getBasenameWoExtension()).strip(".egg")
                models.append(model_path + model_name)

        if self.last_object_index + direction < len(models):
            self.last_object_index += direction
            if self.last_object_index < 0:
                self.last_object_index = len(models) - 1
        else:
            self.last_object_index = 0
        print("model index: ", self.last_object_index)
        self.objectPainter.loadModel(models[self.last_object_index])
        # self.objectPainter.adjustHpr(random.randint(0,72)*5,axis='H: ')
        # self.objectPainter.adjustScale(random.randint(-1,1)*0.05)
        # self.heading_info['text']=self.objectPainter.adjustHpr(0,self.hpr_axis)
        # self.size_info['text']='%.2f'%self.objectPainter.currentScale
        self.last_model_path = model_path

    def setActor(self, model, id=None, guiEvent=None):
        if id != None:
            # self.gui.blink(self.object_toolbar_id, id)
            self.objectPainter.loadActor(model)

    def setObject(self, model, id=None, guiEvent=None):
        if id != None:
            # self.gui.blink(self.object_toolbar_id, id)
            self.objectPainter.loadModel(model)

    def setAxis(self, axis):
        if self.mode == MODE_OBJECT:
            self.hpr_axis = axis
            self.heading_info['text'] = self.objectPainter.adjustHpr(0, axis)
        else:
            return

    def setObjectMode(self, mode, guiEvent=None):
        self.gui.grayOutButtons(self.mode_toolbar_id, (0, 6), mode)
        self.object_mode = mode
        if guiEvent != None:
            self.objectPainter.stop()
        if mode == OBJECT_MODE_ONE:
            self.gui.showElement(self.object_toolbar_id)
            self.gui.hideElement(self.multi_toolbar_id)
            self.gui.hideElement(self.wall_toolbar_id)
            self.gui.hideElement(self.actor_toolbar_id)
            self.gui.hideElement(self.collision_toolbar_id)
            self.gui.hideElement(self.select_toolbar_id)
            self.objectPainter.pickerNode.setFromCollideMask(BitMask32.bit(1))
        if mode == OBJECT_MODE_MULTI:
            self.gui.showElement(self.multi_toolbar_id)
            self.gui.hideElement(self.object_toolbar_id)
            self.gui.hideElement(self.wall_toolbar_id)
            self.gui.hideElement(self.actor_toolbar_id)
            self.gui.hideElement(self.collision_toolbar_id)
            self.gui.hideElement(self.select_toolbar_id)
            self.objectPainter.pickerNode.setFromCollideMask(BitMask32.bit(1))
        if mode == OBJECT_MODE_WALL:
            self.gui.showElement(self.wall_toolbar_id)
            self.gui.hideElement(self.object_toolbar_id)
            self.gui.hideElement(self.multi_toolbar_id)
            self.gui.hideElement(self.actor_toolbar_id)
            self.gui.hideElement(self.collision_toolbar_id)
            self.gui.hideElement(self.select_toolbar_id)
            self.objectPainter.pickerNode.setFromCollideMask(BitMask32.bit(1))
        if mode == OBJECT_MODE_SELECT:
            self.gui.hideElement(self.object_toolbar_id)
            self.gui.hideElement(self.multi_toolbar_id)
            self.gui.hideElement(self.wall_toolbar_id)
            self.gui.hideElement(self.actor_toolbar_id)
            self.gui.hideElement(self.collision_toolbar_id)
            self.objectPainter.pickerNode.setFromCollideMask(BitMask32.bit(2))
        if mode == OBJECT_MODE_ACTOR:
            self.gui.showElement(self.actor_toolbar_id)
            self.gui.hideElement(self.object_toolbar_id)
            self.gui.hideElement(self.multi_toolbar_id)
            self.gui.hideElement(self.wall_toolbar_id)
            self.gui.hideElement(self.collision_toolbar_id)
            self.gui.hideElement(self.select_toolbar_id)
            self.objectPainter.pickerNode.setFromCollideMask(BitMask32.bit(1))
        if mode == OBJECT_MODE_COLLISION:
            self.gui.showElement(self.collision_toolbar_id)
            self.gui.hideElement(self.object_toolbar_id)
            self.gui.hideElement(self.multi_toolbar_id)
            self.gui.hideElement(self.wall_toolbar_id)
            self.gui.hideElement(self.actor_toolbar_id)
            self.gui.hideElement(self.select_toolbar_id)
            self.objectPainter.pickerNode.setFromCollideMask(BitMask32.bit(1))

    def hideDialog(self, guiEvent=None):
        self.gui.dialog.hide()

    def onToolbarHover(self, hoverIn, guiEvent=None):
        if self.ignoreHover:
            return
        if hoverIn:
            self.painter.hideBrushes()
        else:
            self.setMode(self.mode)

    def showSaveMenu(self, guiEvent=None):
        self.ignoreHover = True
        self.painter.hideBrushes()
        self.gui.SaveLoadFrame.show()
        self.ignore('mouse1-up')
        self.ignore('mouse1')

    def hideSaveMenu(self, guiEvent=None):
        self.ignoreHover = False
        self.gui.SaveLoadFrame.hide()
        self.setMode(self.mode)

    def CreateGrassTile(self, uv_offset, pos, parent, fogcenter=Vec3(0, 0, 0), count=256):
        grass = loader.loadModel("data/grass_big")
        # grass.setTwoSided(True)
        grass.setTransparency(TransparencyAttrib.MBinary, 1)
        grass.reparentTo(parent)
        grass.setInstanceCount(count)
        grass.node().setBounds(BoundingBox((0, 0, 0), (256, 256, 128)))
        grass.node().setFinal(1)
        grass.setShader(Shader.load(Shader.SLGLSL, cfg["shader_grass_v"], cfg["shader_grass_f"]))
        # grass.setShader(Shader.load(Shader.SLGLSL, "shaders/grass_v.glsl", "shaders/grass_f.glsl"))
        grass.setShaderInput('height', self.painter.textures[BUFFER_HEIGHT])
        grass.setShaderInput('grass', self.painter.textures[BUFFER_GRASS])
        grass.setShaderInput('uv_offset', uv_offset)
        grass.setShaderInput('fogcenter', fogcenter)
        grass.setPos(pos)
        return grass

    def load(self, guiEvent=None):
        save_dir = path + self.gui.entry1.get()
        feedback = ""
        if self.gui.flags[0]:  # height map
            print("loading height map...", end=' ')
            file = path + save_dir + "/" + self.gui.entry2.get() + '.png'
            if exists(file):
                self.painter.paintPlanes[BUFFER_HEIGHT].setTexture(loader.loadTexture(file))
                print("done")
            else:
                print("FILE NOT FOUND!")
                feedback += file + ' '
        if self.gui.flags[1]:  # atr map, both
            print("loading detail map...", end=' ')
            file = path + save_dir + "/" + self.gui.entry3.get() + '0.png'
            if exists(file):
                self.painter.paintPlanes[BUFFER_ATR].setTexture(loader.loadTexture(file))
                print("ok...", end=' ')
            else:
                print("FILE NOT FOUND!")
                feedback += file + ' '
            file = path + save_dir + "/" + self.gui.entry3.get() + '1.png'
            if exists(file):
                self.painter.paintPlanes[BUFFER_ATR2].setTexture(loader.loadTexture(file))
                print("done")
            else:
                print("FILE NOT FOUND!")
                feedback += file + ' '
        if self.gui.flags[2]:  # grass map
            print("loading grass map...", end=' ')
            file = path + save_dir + "/" + self.gui.entry5.get() + '.png'
            if exists(file):
                self.painter.paintPlanes[BUFFER_GRASS].setTexture(loader.loadTexture(file))
                print("done")
            else:
                print("FILE NOT FOUND!")
                feedback += file + ' '
        if self.gui.flags[4]:  # objects and textures used for terrain
            print("loading objects", end=' ')
            file = path + save_dir + "/" + self.gui.entry6.get()
            data = LoadScene(file,
                             self.objectPainter.quadtree,
                             self.objectPainter.actors,
                             self.mesh,
                             self.textures_diffuse,
                             self.curent_textures,
                             self.grass,
                             self.grass_textures,
                             self.current_grass_textures)
            if data:
                i = 0
                for id in self.curent_textures:
                    self.gui.elements[self.palette_id]['buttons'][i]['frameTexture'] = self.textures_diffuse[id]
                    i += 1
                i = 0
                for id in self.current_grass_textures:
                    self.gui.elements[self.grass_toolbar_id]['buttons'][i]['frameTexture'] = self.grass_textures[id]
                    i += 1
                # load sky and water data
                self.gui.setSkySeaValues(data)

                TerrainTile = self.gui.SkySeaOptions[0]
                TerrainScale = self.gui.SkySeaOptions[1]
                SkyTile = self.gui.SkySeaOptions[2]
                CloudSpeed = self.gui.SkySeaOptions[3]
                WaveTile = self.gui.SkySeaOptions[4]
                WaveHeight = self.gui.SkySeaOptions[5]
                WaveXYMove = [self.gui.SkySeaOptions[6][0], self.gui.SkySeaOptions[6][1]]
                WaterTile = self.gui.SkySeaOptions[7]
                WaterSpeed = self.gui.SkySeaOptions[8]
                WaterLevel = self.gui.SkySeaOptions[9]

                self.skydome.setShaderInput("cloudTile", SkyTile)
                self.skydome.setShaderInput("cloudSpeed", CloudSpeed)
                self.mesh.setShaderInput("water_level", WaterLevel)
                render.setShaderInput("z_scale", TerrainScale)
                self.mesh.setShaderInput("tex_scale", TerrainTile)
                if WaterLevel > 0.0:
                    self.wBuffer.setActive(True)
                    self.waterNP.show()
                    self.waterNP.setShaderInput("tile", WaterTile)
                    self.waterNP.setShaderInput("speed", WaterSpeed)
                    self.waterNP.setShaderInput("water_level", WaterLevel)
                    self.waterNP.setShaderInput("wave", Vec4(WaveXYMove[0], WaveXYMove[1], WaveTile, WaveHeight))
                    self.waterNP.setPos(0, 0, WaterLevel)
                    self.wPlane = Plane(Vec3(0, 0, 1), Point3(0, 0, WaterLevel))
                    wPlaneNP = render.attachNewNode(PlaneNode("water", self.wPlane))
                    self.mesh.setShaderInput("water_level", WaterLevel)
                    tmpNP = NodePath("StateInitializer")
                    tmpNP.setClipPlane(wPlaneNP)
                    tmpNP.setAttrib(CullFaceAttrib.makeReverse())
                    self.waterCamera.node().setInitialState(tmpNP.getState())
                else:
                    self.waterNP.hide()
                    self.wBuffer.setActive(False)
                    self.mesh.setShaderInput("water_level", -10.0)
                self.findLights()
                print("done")
            else:
                print("FILE NOT FOUND!")
                feedback += file + ' '
        if self.gui.flags[5]:  # collision
            print("loading collision mesh...", end=' ')
            file = path + save_dir + "/" + self.gui.entry7.get() + '.egg'
            if exists(file):
                if self.collision_mesh:
                    self.collision_mesh.removeNode()
                self.collision_mesh = loader.loadModel(file)
                self.collision_mesh.reparentTo(render)
                self.collision_mesh.setCollideMask(BitMask32.bit(1))
                print("done")
            else:
                print("FILE NOT FOUND!")
                feedback += file + ' '
        if self.gui.flags[6]:  # nav map
            print("loading navigation map...", end=' ')
            file = path + save_dir + "/" + self.gui.entry8.get() + ".png"
            if exists(file):
                self.painter.paintPlanes[BUFFER_WALK].setTexture(loader.loadTexture(file))
                print("done")
            else:
                print("FILE NOT FOUND!")
                feedback += file + ' '
        print("Loading DONE!")
        if feedback != "":
            self.gui.okDialog(text="Some files are missing:\n" + feedback, command=self.hideDialog)
        self.hideSaveMenu()

    def save(self, override, guiEvent=None):
        save_dir = path + self.gui.entry1.get()
        if exists(path + save_dir):
            if override == "ASK":
                self.gui.yesNoDialog(text=save_dir + " already exists! \nOverride files?", command=self.save, arg=[])
                self.gui.SaveLoadFrame.hide()
                return
            if override == False:
                self.gui.dialog.hide()
                self.hideSaveMenu()
                return
        else:
            makedirs(Filename(path + save_dir).toOsSpecific())
        if self.gui.flags[0]:  # height map
            print("saving height map...", end=' ')
            self.painter.write(BUFFER_HEIGHT, path + save_dir + "/" + self.gui.entry2.get() + '.png')
            print("done")
        if self.gui.flags[1]:  # atr maps
            print("saving detail map...", end=' ')
            self.painter.write(BUFFER_ATR, path + save_dir + "/" + self.gui.entry3.get() + '0.png')
            print("ok... ")
            self.painter.write(BUFFER_ATR2, path + save_dir + "/" + self.gui.entry3.get() + '1.png')
            print("done")
        if self.gui.flags[2]:  # grass map
            print("saving grass map...", end=' ')
            self.painter.write(BUFFER_GRASS, path + save_dir + "/" + self.gui.entry5.get() + '.png')
            print("done")
        if self.gui.flags[4]:  # objects and textures used
            print("saving objects...", end=' ')
            # sky and water data
            TerrainTile = self.gui.SkySeaOptions[0]
            TerrainScale = self.gui.SkySeaOptions[1]
            SkyTile = self.gui.SkySeaOptions[2]
            CloudSpeed = self.gui.SkySeaOptions[3]
            WaveTile = self.gui.SkySeaOptions[4]
            WaveHeight = self.gui.SkySeaOptions[5]
            WaveXYMove = [self.gui.SkySeaOptions[6][0], self.gui.SkySeaOptions[6][1]]
            WaterTile = self.gui.SkySeaOptions[7]
            WaterSpeed = self.gui.SkySeaOptions[8]
            WaterLevel = self.gui.SkySeaOptions[9]

            sky_water = {'TerrainTile': TerrainTile,
                         'TerrainScale': TerrainScale,
                         'SkyTile': SkyTile,
                         'CloudSpeed': CloudSpeed,
                         'WaveTile': WaveTile,
                         'WaveHeight': WaveHeight,
                         'WaveXYMove': WaveXYMove,
                         'WaterTile': WaterTile,
                         'WaterSpeed': WaterSpeed,
                         'WaterLevel': WaterLevel,
                         }
            tex = []
            for id in self.curent_textures:
                tex.append(self.textures_diffuse[id])
            grs = []
            for id in self.current_grass_textures:
                grs.append(self.grass_textures[id])
            extra_data = [sky_water, {'textures': tex}, {'grass': grs}]
            SaveScene(path + save_dir + "/" + self.gui.entry6.get() + '.json', self.objectPainter.quadtree, extra_data)
            print("done")
        if self.gui.flags[5]:  # collison
            print("saving collision mesh...", end=' ')
            self.genCollision(True, path + save_dir + "/" + self.gui.entry7.get() + '.egg')
            print("done")
        if self.gui.flags[6]:  # navmesh
            print("saving Navigation Mesh(CSV) and map...", end=' ')
            map = self.painter.write(BUFFER_WALK, path + save_dir + "/" + self.gui.entry8.get() + '.png', True)
            GenerateNavmeshCSV(map, path + save_dir + "/" + self.gui.entry8.get() + '.csv')
            print("done")
        print("SAVING DONE!")
        self.gui.okDialog(text="Files saved to:\n" + save_dir, command=self.hideDialog)
        self.hideSaveMenu()

    def setTex(self, layer, id, guiEvent=None):
        self.curent_textures[layer] = id

        new_tex = loader.loadTexture(self.textures_diffuse[id], anisotropicDegree=2)
        if ConfigVariableBool('framebuffer-srgb', False).getValue():
            tex_format = new_tex.getFormat()
            if tex_format == Texture.F_rgb:
                tex_format = Texture.F_srgb
            elif tex_format == Texture.F_rgba:
                tex_format = Texture.F_srgb_alpha
            new_tex.setFormat(tex_format)

        self.mesh.setTexture(self.mesh.findTextureStage('tex' + str(layer + 1)), new_tex, 1)
        self.mesh.setTexture(self.mesh.findTextureStage('tex' + str(layer + 1) + 'n'),
                             loader.loadTexture(self.textures_normal[id], anisotropicDegree=2), 1)
        self.gui.elements[self.palette_id]['buttons'][layer]['frameTexture'] = self.textures_diffuse[id]

    def changeTex(self, layer, guiEvent=None):
        id = self.curent_textures[layer] + 1
        while id in self.curent_textures:
            if id > len(self.textures_diffuse) - 1:
                id = 0
            else:
                id += 1
        if id > len(self.textures_diffuse) - 1:
            id = 0
        self.curent_textures[layer] = id

        new_tex = loader.loadTexture(self.textures_diffuse[id], anisotropicDegree=2)
        if ConfigVariableBool('framebuffer-srgb', False).getValue():
            tex_format = new_tex.getFormat()
            if tex_format == Texture.F_rgb:
                tex_format = Texture.F_srgb
            elif tex_format == Texture.F_rgba:
                tex_format = Texture.F_srgb_alpha
            new_tex.setFormat(tex_format)

        self.mesh.setTexture(self.mesh.findTextureStage('tex' + str(layer + 1)), new_tex, 1)
        self.mesh.setTexture(self.mesh.findTextureStage('tex' + str(layer + 1) + 'n'),
                             loader.loadTexture(self.textures_normal[id], anisotropicDegree=2), 1)
        self.gui.elements[self.palette_id]['buttons'][layer]['frameTexture'] = self.textures_diffuse[id]

    def changeGrassTex(self, layer, guiEvent=None):
        id = self.current_grass_textures[layer] + 1
        while id in self.current_grass_textures:
            if id > len(self.grass_textures) - 1:
                id = 0
            else:
                id += 1
        if id > len(self.grass_textures) - 1:
            id = 0
        self.current_grass_textures[layer] = id
        grass_tex = loader.loadTexture(self.grass_textures[id])
        grass_tex.setWrapU(Texture.WMClamp)
        grass_tex.setWrapV(Texture.WMClamp)
        grass_tex.setMinfilter(Texture.FTLinearMipmapLinear)
        grass_tex.setMagfilter(Texture.FTLinear)
        self.grass.setTexture(self.grass.findTextureStage('tex' + str(layer + 1)), grass_tex, 1)
        self.gui.elements[self.grass_toolbar_id]['buttons'][layer]['frameTexture'] = self.grass_textures[id]

    def setBrush(self, id, guiEvent=None):
        self.painter.setBrushTex(id)
        for button in self.gui.elements[0]['buttons']:
            button.setColor(0, 0, 0, 1)
        self.gui.elements[0]['buttons'][id].setColor(0, 0.4, 0, 1)

    def paint(self):
        if self.mode == MODE_OBJECT:
            self.props['focus'] = 0
            self.snap['focus'] = 0
            props = self.props.get()
            if self.object_mode in (OBJECT_MODE_ONE, OBJECT_MODE_COLLISION, OBJECT_MODE_ACTOR):
                self.objectPainter.drop(props)
                self.props.set('')
            elif self.object_mode == OBJECT_MODE_PICKUP:
                if self.objectPainter.pickup():
                    self.setObjectMode(OBJECT_MODE_ONE)
                    self.heading_info['text'] = self.objectPainter.adjustHpr(0, self.hpr_axis)
                    self.size_info['text'] = '%.2f' % self.objectPainter.currentScale
                    self.color_info['text'] = '%.2f' % self.objectPainter.currentZ
                    self.props.set(self.objectPainter.currentObject.getPythonTag('props'))
            elif self.object_mode == OBJECT_MODE_MULTI:
                self.objectPainter.drop(props)
                self.setNextObject()
            elif self.object_mode == OBJECT_MODE_WALL:
                self.objectPainter.drop(props)
                self.objectPainter.currentObject = render.attachNewNode('temp')
                self.setRandomWall()
            elif self.object_mode == OBJECT_MODE_SELECT:
                if self.objectPainter.select():
                    self.gui.showElement(self.select_toolbar_id)
                    pos = self.objectPainter.selectedObject.getPos()
                    hpr = self.objectPainter.selectedObject.getHpr()
                    scale = self.objectPainter.selectedObject.getScale()
                    props = self.objectPainter.selectedObject.getPythonTag('props')
                    self.gui.elements[self.select_toolbar_id]['buttons'][0].enterText('%.2f' % pos[0])
                    self.gui.elements[self.select_toolbar_id]['buttons'][1].enterText('%.2f' % pos[1])
                    self.gui.elements[self.select_toolbar_id]['buttons'][2].enterText('%.2f' % pos[2])
                    self.gui.elements[self.select_toolbar_id]['buttons'][3].enterText('%.2f' % (hpr[0] % 360.0))
                    self.gui.elements[self.select_toolbar_id]['buttons'][4].enterText('%.2f' % (hpr[1] % 360.0))
                    self.gui.elements[self.select_toolbar_id]['buttons'][5].enterText('%.2f' % (hpr[2] % 360.0))
                    self.gui.elements[self.select_toolbar_id]['buttons'][6].enterText('%.2f' % scale[0])
                    self.props.enterText(props)
                    if self.objectPainter.selectedObject.hasPythonTag('hasLight'):
                        self.gui.colorPickerFrame.show()
                        id = self.objectPainter.selectedObject.getPythonTag('hasLight')
                        color = [int(self.light_manager.lights[id][4] * 255),
                                 int(self.light_manager.lights[id][5] * 255),
                                 int(self.light_manager.lights[id][6] * 255)]
                        self.gui.colorEntry.set(str(color)[1:-1])
                        self.gui.overrideColor()

    def setMode(self, mode, guiEvent=None):
        if mode == MODE_HEIGHT:
            if guiEvent != None:
                self.painter.brushAlpha = 0.05
                self.color_info['text'] = '%.2f' % self.painter.brushAlpha
            self.gui.grayOutButtons(self.statusbar, (4, 9), 4)
            self.painter.brushes[BUFFER_HEIGHT].show()
            self.painter.setBrushIDColor(BUFFER_HEIGHT,
                                         (self.tempColor, self.tempColor, self.tempColor, self.painter.brushAlpha),
                                         False)
            self.painter.brushes[BUFFER_ATR].hide()
            self.painter.brushes[BUFFER_ATR2].hide()
            self.painter.brushes[BUFFER_GRASS].hide()
            self.painter.brushes[BUFFER_WALK].hide()
            self.painter.pointer.show()
            self.hpr_axis = ''
            self.accept('mouse1', self.keyMap.__setitem__, ['paint', True])
            self.accept('mouse1-up', self.keyMap.__setitem__, ['paint', False])
            self.gui.hideElement(self.palette_id)
            self.gui.showElement(self.toolbar_id)
            self.gui.showElement(self.heightmode_toolbar_id)
            self.gui.hideElement(self.mode_toolbar_id)
            self.gui.hideElement(self.object_toolbar_id)
            self.gui.hideElement(self.multi_toolbar_id)
            self.gui.hideElement(self.wall_toolbar_id)
            self.gui.hideElement(self.actor_toolbar_id)
            self.gui.hideElement(self.collision_toolbar_id)
            self.gui.hideElement(self.prop_panel_id)
            self.gui.hideElement(self.walkmap_toolbar_id)
            self.gui.hideElement(self.grass_toolbar_id)
            self.gui.hideElement(self.select_toolbar_id)
            self.gui.hideElement(self.color_toolbar)
            self.objectPainter.stop()
            self.mesh.setShaderInput("walkmap", loader.loadTexture('data/walkmap.png'))
            self.mesh.setShader(Shader.load(Shader.SLGLSL, cfg["shader_terrain_v"], cfg["shader_terrain_f"]))
            render.setShaderInput("show_lights", 0.0)
        elif mode == MODE_TEXTURE:
            if guiEvent != None:
                self.painter.brushAlpha = 1.0
                self.color_info['text'] = '%.2f' % self.painter.brushAlpha
            self.gui.grayOutButtons(self.statusbar, (4, 9), 5)
            self.painter.brushes[BUFFER_HEIGHT].hide()
            self.painter.brushes[BUFFER_ATR].show()
            self.painter.brushes[BUFFER_ATR2].show()
            self.painter.brushes[BUFFER_GRASS].hide()
            self.painter.brushes[BUFFER_WALK].hide()
            self.painter.pointer.show()
            self.hpr_axis = ''
            self.accept('mouse1', self.keyMap.__setitem__, ['paint', True])
            self.accept('mouse1-up', self.keyMap.__setitem__, ['paint', False])
            self.gui.showElement(self.palette_id)
            self.gui.showElement(self.toolbar_id)
            self.gui.hideElement(self.mode_toolbar_id)
            self.gui.hideElement(self.object_toolbar_id)
            self.gui.hideElement(self.multi_toolbar_id)
            self.gui.hideElement(self.wall_toolbar_id)
            self.gui.hideElement(self.actor_toolbar_id)
            self.gui.hideElement(self.collision_toolbar_id)
            self.gui.hideElement(self.prop_panel_id)
            self.gui.hideElement(self.heightmode_toolbar_id)
            self.gui.hideElement(self.walkmap_toolbar_id)
            self.gui.hideElement(self.grass_toolbar_id)
            self.gui.hideElement(self.select_toolbar_id)
            self.gui.hideElement(self.color_toolbar)
            self.objectPainter.stop()
            self.mesh.setShaderInput("walkmap", loader.loadTexture('data/walkmap.png'))
            self.mesh.setShader(Shader.load(Shader.SLGLSL, cfg["shader_terrain_v"], cfg["shader_terrain_f"]))
            render.setShaderInput("show_lights", 0.0)
        elif mode == MODE_GRASS:
            if guiEvent != None:
                self.painter.brushAlpha = 1.0
                self.color_info['text'] = '%.2f' % self.painter.brushAlpha
            self.gui.grayOutButtons(self.statusbar, (4, 9), 6)
            self.painter.brushes[BUFFER_HEIGHT].hide()
            self.painter.brushes[BUFFER_ATR].hide()
            self.painter.brushes[BUFFER_ATR2].hide()
            self.painter.brushes[BUFFER_WALK].hide()
            self.painter.brushes[BUFFER_GRASS].show()
            # self.painter.brushes[BUFFER_GRASS].setColor(1,0,0, self.painter.brushAlpha)
            self.painter.pointer.show()
            self.hpr_axis = ''
            self.accept('mouse1', self.keyMap.__setitem__, ['paint', True])
            self.accept('mouse1-up', self.keyMap.__setitem__, ['paint', False])
            self.gui.hideElement(self.palette_id)
            self.gui.showElement(self.toolbar_id)
            self.gui.hideElement(self.mode_toolbar_id)
            self.gui.hideElement(self.object_toolbar_id)
            self.gui.hideElement(self.multi_toolbar_id)
            self.gui.hideElement(self.wall_toolbar_id)
            self.gui.hideElement(self.actor_toolbar_id)
            self.gui.hideElement(self.collision_toolbar_id)
            self.gui.hideElement(self.prop_panel_id)
            self.gui.hideElement(self.heightmode_toolbar_id)
            self.gui.hideElement(self.walkmap_toolbar_id)
            self.gui.showElement(self.grass_toolbar_id)
            self.gui.hideElement(self.select_toolbar_id)
            self.gui.hideElement(self.color_toolbar)
            self.objectPainter.stop()
            self.mesh.setShaderInput("walkmap", loader.loadTexture('data/walkmap.png'))
            self.mesh.setShader(Shader.load(Shader.SLGLSL, cfg["shader_terrain_v"], cfg["shader_terrain_f"]))
            render.setShaderInput("show_lights", 0.0)
        elif mode == MODE_OBJECT:
            if guiEvent != None:
                self.hpr_axis = 'H: '
                if self.collision_mesh == None:
                    self.gui.yesNoDialog("To place objects a collision mesh is needed.\nGenerate Collision Mesh?",
                                         self.genCollision, ['temp/collision.egg'])
            self.painter.hideBrushes()
            self.painter.pointer.hide()
            self.gui.grayOutButtons(self.statusbar, (4, 9), 7)
            self.gui.hideElement(self.palette_id)
            self.gui.hideElement(self.toolbar_id)
            self.gui.hideElement(self.heightmode_toolbar_id)
            self.gui.showElement(self.mode_toolbar_id)
            self.gui.showElement(self.prop_panel_id)
            self.gui.hideElement(self.walkmap_toolbar_id)
            self.gui.hideElement(self.grass_toolbar_id)
            self.gui.showElement(self.color_toolbar)
            self.setObjectMode(self.object_mode)
            self.accept('mouse1', self.paint)
            self.ignore('mouse1-up')
            self.mesh.setShaderInput("walkmap", self.painter.textures[BUFFER_WALK])
            self.mesh.setShader(Shader.load(Shader.SLGLSL, cfg["shader_terrain_w_v"], cfg["shader_terrain_w_f"]))
            render.setShaderInput("show_lights", 0.3)
        elif mode == MODE_WALK:
            if guiEvent != None:
                self.painter.brushAlpha = 1.0
                self.color_info['text'] = '%.2f' % self.painter.brushAlpha
                self.changeWalkMode(WALK_MODE_NOWALK)
            self.gui.grayOutButtons(self.statusbar, (4, 9), 8)
            self.painter.brushes[BUFFER_HEIGHT].hide()
            self.painter.brushes[BUFFER_ATR].hide()
            self.painter.brushes[BUFFER_ATR2].hide()
            self.painter.brushes[BUFFER_GRASS].hide()
            self.painter.brushes[BUFFER_WALK].show()
            self.painter.pointer.show()
            self.hpr_axis = ''
            self.accept('mouse1', self.keyMap.__setitem__, ['paint', True])
            self.accept('mouse1-up', self.keyMap.__setitem__, ['paint', False])
            self.gui.hideElement(self.palette_id)
            self.gui.showElement(self.toolbar_id)
            self.gui.hideElement(self.mode_toolbar_id)
            self.gui.hideElement(self.object_toolbar_id)
            self.gui.hideElement(self.multi_toolbar_id)
            self.gui.hideElement(self.wall_toolbar_id)
            self.gui.hideElement(self.actor_toolbar_id)
            self.gui.hideElement(self.collision_toolbar_id)
            self.gui.hideElement(self.prop_panel_id)
            self.gui.hideElement(self.heightmode_toolbar_id)
            self.gui.showElement(self.walkmap_toolbar_id)
            self.gui.hideElement(self.grass_toolbar_id)
            self.gui.hideElement(self.select_toolbar_id)
            self.gui.hideElement(self.color_toolbar)
            self.objectPainter.stop()
            self.mesh.setShaderInput("walkmap", self.painter.textures[BUFFER_WALK])
            self.mesh.setShader(Shader.load(Shader.SLGLSL, cfg["shader_terrain_w_v"], cfg["shader_terrain_w_f"]))
            render.setShaderInput("show_lights", 0.0)
        self.mode = mode
        self.heading_info['text'] = self.hpr_axis + '%.0f' % self.painter.brushes[0].getH()

    def genCollision(self, yes, file, guiEvent=None):
        if yes:
            if guiEvent != None:
                self.gui.dialog.hide()
                self.gui.wait.show()
                base.graphicsEngine.renderFrame()
                base.graphicsEngine.renderFrame()
            heightmap = PNMImage(self.painter.buffSize[BUFFER_HEIGHT], self.painter.buffSize[BUFFER_HEIGHT], 4)
            base.graphicsEngine.extractTextureData(self.painter.textures[BUFFER_HEIGHT], base.win.getGsg())
            self.painter.textures[BUFFER_HEIGHT].store(heightmap)
            GenerateCollisionEgg(heightmap, file, input='data/collision80k.egg', scale=self.gui.SkySeaOptions[1])
            if self.collision_mesh:
                self.collision_mesh.removeNode()
            print("Loading mesh...")
            self.collision_mesh = loader.loadModel(file, noCache=True)
            self.collision_mesh.reparentTo(render)
            self.collision_mesh.setCollideMask(BitMask32.bit(1))
        if guiEvent != None:
            self.gui.dialog.hide()
            if yes:
                self.gui.wait.hide()
                self.gui.okDialog(text="Collision mesh saved to:\n" + file, command=self.hideDialog)

    def nextModel(self):
        if self.mode == MODE_OBJECT:
            if self.object_mode == OBJECT_MODE_MULTI:
                self.setNextObject()
            if self.object_mode == OBJECT_MODE_WALL:
                self.nextWall()

    def previousModel(self):
        if self.mode == MODE_OBJECT:
            if self.object_mode == OBJECT_MODE_MULTI:
                self.setNextObject(direction=-1)
            if self.object_mode == OBJECT_MODE_WALL:
                self.nextWall(direction=-1)

    def update(self):
        if self.mode == MODE_HEIGHT:
            if self.keyMap['paint']:
                self.painter.paint(BUFFER_HEIGHT)
        elif self.mode == MODE_GRASS:
            if self.keyMap['paint']:
                self.painter.paint(BUFFER_GRASS)
        elif self.mode == MODE_TEXTURE:
            if self.keyMap['paint']:
                self.painter.paint(BUFFER_ATR)
                self.painter.paint(BUFFER_ATR2)
        elif self.mode == MODE_WALK:
            if self.keyMap['paint']:
                self.painter.paint(BUFFER_WALK)
        elif self.mode == MODE_OBJECT:
            if self.keyMap['rotate_l']:
                self.heading_info['text'] = self.objectPainter.adjustHpr(-0.5, self.hpr_axis)
            if self.keyMap['rotate_r']:
                self.heading_info['text'] = self.objectPainter.adjustHpr(0.5, self.hpr_axis)
            if self.keyMap['scale_up']:
                self.objectPainter.adjustScale(0.01)
                self.size_info['text'] = '%.2f' % self.objectPainter.currentScale
            if self.keyMap['scale_down']:
                self.objectPainter.adjustScale(-0.01)
                self.size_info['text'] = '%.2f' % self.objectPainter.currentScale
            if self.keyMap['alpha_up']:
                self.objectPainter.adjustZ(0.05)
                self.color_info['text'] = '%.2f' % self.objectPainter.currentZ
            if self.keyMap['alpha_down']:
                self.objectPainter.adjustZ(-0.05)
                self.color_info['text'] = '%.2f' % self.objectPainter.currentZ
            return

        # if self.mode in (MODE_HEIGHT,MODE_TEXTURE,MODE_GRASS):
        if self.keyMap['rotate_l']:
            self.painter.adjustBrushHeading(5)
            self.heading_info['text'] = self.hpr_axis + '%.0f' % self.painter.brushes[0].getH()
        if self.keyMap['rotate_r']:
            self.painter.adjustBrushHeading(-5)
            self.heading_info['text'] = self.hpr_axis + '%.0f' % self.painter.brushes[0].getH()
        if self.keyMap['scale_up']:
            self.painter.adjustBrushSize(0.01)
            self.size_info['text'] = '%.2f' % self.painter.brushSize
        if self.keyMap['scale_down']:
            self.painter.adjustBrushSize(-0.01)
            self.size_info['text'] = '%.2f' % self.painter.brushSize
        if self.keyMap['alpha_up']:
            if self.mode == MODE_HEIGHT and self.height_mode == HEIGHT_MODE_LEVEL:
                self.tempColor = min(1.0, max(0.0, self.tempColor + 0.01))
                self.painter.setBrushIDColor(BUFFER_HEIGHT, (self.tempColor, self.tempColor, self.tempColor, 1), False)
                self.color_info['text'] = '%.2f' % self.tempColor
            else:
                self.painter.adjustBrushAlpha(0.01)
                self.color_info['text'] = '%.2f' % self.painter.brushAlpha
        if self.keyMap['alpha_down']:
            if self.mode == MODE_HEIGHT and self.height_mode == HEIGHT_MODE_LEVEL:
                self.tempColor = min(1.0, max(0.0, self.tempColor - 0.01))
                self.painter.setBrushIDColor(BUFFER_HEIGHT, (self.tempColor, self.tempColor, self.tempColor, 1), False)
                self.color_info['text'] = '%.2f' % self.tempColor
            else:
                self.painter.adjustBrushAlpha(-0.01)
                self.color_info['text'] = '%.2f' % self.painter.brushAlpha
        return

    def perFrameUpdate(self, task):
        time = globalClock.getFrameTime()
        pos = self.controler.cameraNode.getPos()
        # water
        if self.waterNP.getZ() > 0.0:
            self.waterCamera.setMat(base.cam.getMat(render) * self.wPlane.getReflectionMat())
        if self.lastUpdateTime + 0.03 < time:
            self.update()
            self.lastUpdateTime = time
        if self.mode == MODE_OBJECT:
            self.objectPainter.update(self.snap.get())
        return task.cont

    def windowEventHandler(self, window=None):
        if window is not None:  # window is none if panda3d is not started
            wp = window.getProperties()
            newsize = [wp.getXSize(), wp.getYSize()]
            if self.winsize != newsize:
                self.gui.updateBaseNodes()
                self.filters[-1].setShaderInput("rt_w", float(base.win.getXSize()))
                self.filters[-1].setShaderInput("rt_h", float(base.win.getYSize()))
                if len(self.filters) > 1:
                    self.filters[-2].setShaderInput('screen_size',
                                                    Vec2(float(base.win.getXSize()), float(base.win.getYSize())))

    def setAtrMapColor(self, color1, color2, event=None):
        self.painter.setBrushIDColor(BUFFER_ATR, (color1[0], color1[1], color1[2], self.painter.brushAlpha))
        self.painter.setBrushIDColor(BUFFER_ATR2, (color2[0], color2[1], color2[2], self.painter.brushAlpha))

    def setGrassMapColor(self, color, event=None):
        self.painter.setBrushIDColor(BUFFER_GRASS, (color[0], color[1], color[2], self.painter.brushAlpha))


if __name__ == "__main__":
    app = Editor()
    base.run()
