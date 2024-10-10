import bpy, bmesh
import math
import re
import numpy as np
from mathutils import Vector

np.set_printoptions(suppress=True)  # Suprime notación científica en funciones de subdivisión linspace

class Segment:
    def __init__(self, type, coords, color, toolnumber, lineNb, line):
        self.type = type
        self.coords = coords
        self.color = color
        self.toolnumber = toolnumber
        self.lineNb = lineNb
        self.line = line
        self.style = None
        self.layerIdx = None
        self.distance = None

    def __str__(self):
        return f" <coords={self.coords}, lineNb={self.lineNb}, style={self.style}, layerIdx={self.layerIdx}, color={self.color}>"

class GcodeModel:
    def __init__(self, parser):
        self.parser = parser
        self.relative = {
            "X":0.0,
            "Y":0.0,
            "Z":0.0,
            "F":0.0,
            "E":0.0}
        self.offset = {
            "X":0.0,
            "Y":0.0,
            "Z":0.0,
            "E":0.0}
        self.isRelative = False
        self.color = [0,0,0,0,0,0,0,0]  # RGBCMYKW
        self.toolnumber = 0
        self.segments = []
        self.layers = []

    def do_G1(self, args, type):
        coords = dict(self.relative)
        for axis in args.keys():
            if axis in coords:
                if self.isRelative: 
                    coords[axis] += args[axis]
                else:
                    coords[axis] = args[axis]
            else:
                self.warn(f"Unknown axis '{axis}'")
        
        absolute = {
            "X": self.offset["X"] + coords["X"],
            "Y": self.offset["Y"] + coords["Y"],
            "Z": self.offset["Z"] + coords["Z"],
            "F": coords["F"]
        }

        if "E" not in args:
            absolute["E"] = 0
        else:
            absolute["E"] = args["E"]

        seg = Segment(
            type,
            absolute,
            self.color.copy(),
            self.toolnumber,
            self.parser.lineNb,
            self.parser.line
        )
        
        if seg.coords['X'] != self.relative['X'] + self.offset["X"] or \
           seg.coords['Y'] != self.relative['Y'] + self.offset["Y"] or \
           seg.coords['Z'] != self.relative['Z'] + self.offset["Z"]:
            self.addSegment(seg)
        
        self.relative = coords

    def do_G0(self, args, type):
        self.do_G1(args, type=type)

    def do_G90(self, args):
        self.isRelative = False

    def do_G91(self, args):
        self.isRelative = True

    def do_G92(self, args):
        if not len(args.keys()):
            args = {"X":0.0, "Y":0.0, "Z":0.0}
        for axis in args.keys():
            if axis in self.offset:
                self.offset[axis] += self.relative[axis] - args[axis]
                self.relative[axis] = args[axis]
            else:
                self.warn(f"Unknown axis '{axis}'")

    def do_M163(self, args):
        extr_idx = int(args.get('S', 0))  # e.g., M163 S0 P1
        weight = args.get('P', 1.0)
        if extr_idx < 0 or extr_idx >= len(self.color) - 3:
            self.warn(f"Extruder index '{extr_idx}' out of range.")
            return
        self.color[extr_idx+3] = weight  # CMYKW
        # Extraer RGB de comentarios
        if self.parser.comment:
            try:
                RGB = eval(self.parser.comment[:3])
                if isinstance(RGB, (list, tuple)) and len(RGB) == 3:
                    self.color[:3] = RGB
            except:
                pass

    def parseArgs(self, args):
        dic = {}
        if args:
            bits = args.split()
            for bit in bits:
                letter = bit[0]
                try:
                    coord = float(bit[1:])
                except ValueError:
                    coord = 1.0
                dic[letter] = coord
        return dic

    def parseLine(self):
        bits = self.parser.line.split(';',1)
        if len(bits) > 1:
            self.parser.comment = bits[1]
        
        command = bits[0].strip()
        comm = command.split(None, 1)
        code = comm[0] if len(comm) > 0 else None
        args = comm[1] if len(comm) > 1 else None
        
        if code:
            method_name = f"do_{code}"
            if hasattr(self, method_name):
                if code in ['G0', 'G1']:
                    getattr(self, method_name)(self.parseArgs(args), type=code)
                else:
                    getattr(self, method_name)(self.parseArgs(args))
            else:
                if code.startswith("T"):
                    try:
                        self.toolnumber = int(code[1:])
                    except ValueError:
                        self.warn(f"Invalid tool number in code '{code}'.")
                else:
                    pass  # Código desconocido

    def parseFile(self, path):
        with open(path, 'r') as f:
            for line in f:
                self.parser.lineNb += 1
                self.parser.line = line.rstrip()
                self.parseLine()
        return self

    def addSegment(self, segment):
        self.segments.append(segment)

    def classifySegments(self):
        coords = {
            "X":0.0,
            "Y":0.0,
            "Z":0.0,
            "F":0.0,
            "E":0.0}
        currentLayerIdx = 0
        currentLayerZ = 0
        layer = []
        
        for i, seg in enumerate(self.segments):
            style = "travel"
            if ((seg.coords["X"] != coords["X"]) or 
                (seg.coords["Y"] != coords["Y"]) or 
                (seg.coords["Z"] != coords["Z"])) and \
                (seg.coords["E"] > 0 ):
                style = "extrude"
            
            # Detectar cambio de capa
            if i < len(self.segments)-1:
                next_seg = self.segments[i+1]
                if seg.coords["Z"] != currentLayerZ and next_seg.coords["E"] > 0:
                    self.layers.append(layer)
                    layer = []
                    currentLayerZ = seg.coords["Z"]
                    currentLayerIdx += 1
            
            seg.style = style
            seg.layerIdx = currentLayerIdx
            layer.append(seg)
            coords = seg.coords
        
        if layer:
            self.layers.append(layer)

    def subdivide_segments(self, subd_threshold):
        subdivided_segs = []
        coords = {
            "X":0.0,
            "Y":0.0,
            "Z":0.0,
            "F":0.0,
            "E":0.0}

        for seg in self.segments:
            d = math.sqrt(
                (seg.coords["X"] - coords["X"])**2 +
                (seg.coords["Y"] - coords["Y"])**2 +
                (seg.coords["Z"] - coords["Z"])**2
            )
            seg.distance = d

            if d > subd_threshold:
                subdivs = math.ceil(d / subd_threshold)
                P1 = coords
                P2 = seg.coords
                interp_coords = np.linspace(list(P1.values()), list(P2.values()), num=subdivs, endpoint=True)

                for i in range(len(interp_coords)):
                    new_coords = {
                        "X": interp_coords[i][0],
                        "Y": interp_coords[i][1],
                        "Z": interp_coords[i][2],
                        "F": seg.coords["F"]
                    }
                    if seg.coords["E"] > 0:
                        new_coords["E"] = round(seg.coords["E"] / (subdivs-1), 5)
                    else:
                        new_coords["E"] = 0
                    
                    if new_coords['X'] != coords['X'] or \
                       new_coords['Y'] != coords['Y'] or \
                       new_coords['Z'] != coords['Z']:
                        new_seg = Segment(seg.type, new_coords, seg.color.copy(), seg.toolnumber, seg.lineNb, seg.line)
                        new_seg.layerIdx = seg.layerIdx
                        new_seg.style = seg.style
                        subdivided_segs.append(new_seg)
            else:
                subdivided_segs.append(seg)
            
            coords = seg.coords

        self.segments = subdivided_segs

    def create_continuous_curve(self, settings):
        verts = []
        for seg in self.segments:
            verts.append((seg.coords['X'], seg.coords['Y'], seg.coords['Z']))
        
        curve_data = bpy.data.curves.new('GCodeContinuousPath', type='CURVE')
        curve_data.dimensions = '3D'
        polyline = curve_data.splines.new('POLY')
        polyline.points.add(len(verts) - 1)
        
        for i, vert in enumerate(verts):
            polyline.points[i].co = (vert[0], vert[1], vert[2], 1)
        
        curve_obj = bpy.data.objects.new('GCodeContinuousCurve', curve_data)
        bpy.context.collection.objects.link(curve_obj)
        return curve_obj

    def create_split_layers(self):
        collection_name = "Layers"
        if collection_name not in bpy.data.collections:
            layers_collection = bpy.data.collections.new(collection_name)
            bpy.context.scene.collection.children.link(layers_collection)
        else:
            layers_collection = bpy.data.collections[collection_name]
        
        for i, layer in enumerate(self.layers):
            verts, edges = self.segments_to_meshdata(layer)
            if len(verts) > 0:
                mesh = bpy.data.meshes.new(f"Layer_{i}")
                mesh.from_pydata(verts, edges, [])
                mesh.update()
                obj = bpy.data.objects.new(f"Layer_{i}", mesh)
                layers_collection.objects.link(obj)

    def segments_to_meshdata(self, segments):
        verts = []
        edges = []
        for seg in segments:
            verts.append((seg.coords['X'], seg.coords['Y'], seg.coords['Z']))
        edges = [(i, i + 1) for i in range(len(verts) - 1)]
        return verts, edges

    def create_filament_object(self, settings):
        if settings.filament_object == 'CYLINDER':
            bpy.ops.mesh.primitive_cylinder_add(
                radius=settings.filament_radius,
                depth=2.0,
                location=(0, 0, 0)
            )
            filament = bpy.context.active_object
            filament.name = "Filamento"
        elif settings.filament_object == 'SPHERE':
            bpy.ops.mesh.primitive_uv_sphere_add(
                radius=settings.filament_radius,
                location=(0, 0, 0)
            )
            filament = bpy.context.active_object
            filament.name = "Filamento"
        elif settings.filament_object == 'CUSTOM':
            if settings.custom_object and settings.custom_object in bpy.data.objects:
                filament = bpy.data.objects[settings.custom_object]
                filament.name = "Filamento"
            else:
                self.warn(f"Objeto personalizado '{settings.custom_object}' no encontrado. Se usará un cilindro por defecto.")
                bpy.ops.mesh.primitive_cylinder_add(
                    radius=settings.filament_radius,
                    depth=2.0,
                    location=(0, 0, 0)
                )
                filament = bpy.context.active_object
                filament.name = "Filamento"
        else:
            bpy.ops.mesh.primitive_cylinder_add(
                radius=settings.filament_radius,
                depth=2.0,
                location=(0, 0, 0)
            )
            filament = bpy.context.active_object
            filament.name = "Filamento"

        # Aplicar bevel
        bpy.context.view_layer.objects.active = filament
        bpy.ops.object.modifier_add(type='BEVEL')
        bevel = filament.modifiers["Bevel"]
        bevel.width = settings.bevel_depth
        bevel.segments = settings.bevel_resolution
        bevel.profile = 0.5
        bpy.ops.object.modifier_apply(modifier="Bevel")

        return filament

class GcodeParser:
    comment = ""  # Comentarios globales para acceder en otras clases

    def __init__(self):
        self.model = GcodeModel(self)
        self.lineNb = 0
        self.line = ""

    def parseFile(self, path):
        with open(path, 'r') as f:
            for line in f:
                self.lineNb += 1
                self.line = line.rstrip()
                self.model.parseLine()
        return self.model

    def warn(self, msg):
        print(f"[WARN] Line {self.lineNb}: {msg} (Text:'{self.line}')")

    def error(self, msg):
        print(f"[ERROR] Line {self.lineNb}: {msg} (Text:'{self.line}')")
        raise Exception(f"[ERROR] Line {self.lineNb}: {msg} (Text:'{self.line}')")
