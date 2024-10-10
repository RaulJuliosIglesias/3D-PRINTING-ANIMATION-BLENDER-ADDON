bl_info = {
    "name": "Importador de G-code para Timelapse de Impresión 3D",
    "blender": (4, 2, 0),
    "category": "Import-Export",
    "author": "Tu Nombre",
    "version": (1, 0),
    "description": "Importa archivos G-code y crea animaciones de filamento para timelapses de impresión 3D",
}

import bpy
from bpy.props import (
    StringProperty,
    BoolProperty,
    PointerProperty,
    FloatProperty,
    EnumProperty,
    IntProperty,
)
from bpy.types import (
    Panel,
    Operator,
    PropertyGroup,
)
from bpy_extras.io_utils import ImportHelper

from . import parser
import math
import numpy as np

# Definición de las propiedades del add-on
class ImportGcodeSettings(PropertyGroup):
    split_layers: BoolProperty(
        name="Separar Capas",
        description="Guardar cada capa como un objeto individual en una colección",
        default=True
    )

    subdivide: BoolProperty(
        name="Subdividir",
        description="Subdividir segmentos de G-code que superen el tamaño de segmento especificado",
        default=False
    )

    max_segment_size: FloatProperty(
        name="Longitud Máxima de Segmento",
        description="Solo se subdividen segmentos mayores a este valor",
        default=1.0,
        min=0.1,
        max=999.0
    )

    create_continuous: BoolProperty(
        name="Crear Curva Continua",
        description="Crear una única curva continua en lugar de objetos separados por capas",
        default=True
    )

    filament_radius: FloatProperty(
        name="Radio del Filamento",
        description="Radio del objeto que representará el filamento",
        default=0.1,
        min=0.01,
        max=10.0
    )

    filament_speed: FloatProperty(
        name="Velocidad del Filamento",
        description="Velocidad de animación del filamento (unidades por frame)",
        default=1.0,
        min=0.1,
        max=10.0
    )

    bevel_depth: FloatProperty(
        name="Profundidad del Bevel",
        description="Profundidad del bevel aplicado al objeto del filamento",
        default=0.02,
        min=0.0,
        max=1.0
    )

    bevel_resolution: IntProperty(
        name="Resolución del Bevel",
        description="Número de segmentos en el bevel",
        default=2,
        min=0,
        max=10
    )

    filament_object: EnumProperty(
        name="Objeto de Filamento",
        description="Objeto a utilizar para representar el filamento",
        items=[
            ('CYLINDER', "Cilindro", "Usar un cilindro como filamento"),
            ('SPHERE', "Esfera", "Usar una esfera como filamento"),
            ('CUSTOM', "Personalizado", "Usar un objeto personalizado")
        ],
        default='CYLINDER'
    )

    custom_object: StringProperty(
        name="Nombre del Objeto Personalizado",
        description="Nombre del objeto personalizado a utilizar como filamento",
        default="",
    )

    extruder_object: StringProperty(
        name="Objeto Extrusor",
        description="Nombre del objeto en la colección de escena que actuará como extrusor",
        default="Extrusor",
    )

# Panel de Importación de G-code
class OBJECT_PT_CustomPanel(Panel):
    bl_label = "Importador de G-code"
    bl_idname = "OBJECT_PT_custom_panel"
    bl_space_type = "VIEW_3D"   
    bl_region_type = "UI"
    bl_category = "Gcode-Import"
    bl_context = "objectmode"   

    @classmethod
    def poll(cls, context):
        return context.mode in {'OBJECT', 'EDIT_MESH'}

    def draw(self, context):
        layout = self.layout
        scene = context.scene
        mytool = scene.gcode_importer_settings

        layout.prop(mytool, "split_layers")
        layout.prop(mytool, "subdivide")

        row = layout.row()
        row.prop(mytool, "max_segment_size")
        row.enabled = mytool.subdivide

        layout.prop(mytool, "create_continuous")
        layout.prop(mytool, "filament_object")

        if mytool.filament_object == 'CUSTOM':
            layout.prop(mytool, "custom_object")

        layout.prop(mytool, "filament_radius")
        layout.prop(mytool, "filament_speed")
        layout.prop(mytool, "bevel_depth")
        layout.prop(mytool, "bevel_resolution")

        layout.separator()

        layout.prop(mytool, "extruder_object")

        layout.separator()

        layout.operator("wm.gcode_import", text="Importar G-code")
        layout.operator("wm.generate_geometry_nodes", text="Generar Geometry Nodes")
        layout.operator("wm.animate_filament", text="Animar Filamento")

# Operador de Importación de G-code
class WM_OT_gcode_import(Operator, ImportHelper):
    """Importar G-code y crear animaciones de filamento"""
    bl_idname = "wm.gcode_import"
    bl_label = "Importar G-code"
    bl_options = {'REGISTER', 'UNDO'}
    
    # ImportHelper mixin class uses this
    filename_ext = ".gcode;*.txt"
    
    filter_glob: StringProperty(
        default="*.gcode;*.txt",
        options={'HIDDEN'},
        maxlen=255,
    )

    def execute(self, context):
        return import_gcode(context, self.filepath)

# Operador para Generar Geometry Nodes
class WM_OT_generate_geometry_nodes(Operator):
    """Generar Geometry Nodes para convertir curva a malla y configurar animación"""
    bl_idname = "wm.generate_geometry_nodes"
    bl_label = "Generar Geometry Nodes"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        settings = context.scene.gcode_importer_settings
        extruder_name = settings.extruder_object

        # Obtener el objeto extrusor
        if extruder_name in bpy.data.objects:
            extruder = bpy.data.objects[extruder_name]
        else:
            self.report({'ERROR'}, f"Objeto extrusor '{extruder_name}' no encontrado.")
            return {'CANCELLED'}

        # Obtener la curva creada
        curve_objs = [obj for obj in bpy.context.scene.objects if obj.type == 'CURVE' and obj.name.startswith("GCode")]
        if not curve_objs:
            self.report({'ERROR'}, "No se encontró ninguna curva. Importa un archivo G-code primero.")
            return {'CANCELLED'}
        curve_obj = curve_objs[-1]  # Seleccionar la última curva importada

        # Obtener el objeto del filamento
        filament = bpy.data.objects.get("Filamento")
        if not filament:
            self.report({'ERROR'}, "Objeto 'Filamento' no encontrado. Genera Geometry Nodes primero.")
            return {'CANCELLED'}

        # Añadir el modificador de Geometry Nodes
        if "GeometryNodes" in filament.modifiers:
            filament.modifiers.remove(filament.modifiers["GeometryNodes"])

        gn_modifier = filament.modifiers.new(name="GeometryNodes", type='NODES')
        node_group = bpy.data.node_groups.new(type="GeometryNodeTree", name="FilamentGeometry")
        gn_modifier.node_group = node_group

        nodes = node_group.nodes
        links = node_group.links

        # Limpiar nodos por defecto
        for node in nodes:
            nodes.remove(node)

        # Crear nodos de entrada y salida
        group_input = nodes.new(type='NodeGroupInput')
        group_input.location = (-800, 0)
        node_group.inputs.new('NodeSocketGeometry', "Geometry")

        group_output = nodes.new(type='NodeGroupOutput')
        group_output.location = (800, 0)
        node_group.outputs.new('NodeSocketGeometry', "Geometry")

        # Geometry Nodes:

        # 1. Object Info Node for the curve
        object_info = nodes.new(type='GeometryNodeObjectInfo')
        object_info.location = (-600, 200)
        object_info.inputs['Object'].default_value = curve_obj

        # 2. Resample Curve Node
        resample_curve = nodes.new(type='GeometryNodeResampleCurve')
        resample_curve.location = (-600, 100)
        resample_curve.inputs['Count'].default_value = 1000

        # 3. Trim Curve Node
        trim_curve = nodes.new(type='GeometryNodeTrimCurve')
        trim_curve.location = (-400, 200)

        # 4. Value Node for animation factor
        value_node = nodes.new(type='ShaderNodeValue')  # ShaderNodeValue es genérico para valores
        value_node.location = (-800, 200)
        value_node.outputs['Value'].default_value = 0.0
        # Insertar keyframes para animación
        value_node.outputs['Value'].keyframe_insert(data_path="default_value", frame=1)
        value_node.outputs['Value'].default_value = 1.0
        value_node.outputs['Value'].keyframe_insert(data_path="default_value", frame=250)

        # 5. Fillet Curve Node
        fillet_curve = nodes.new(type='GeometryNodeFilletCurve')
        fillet_curve.location = (-200, 200)
        fillet_curve.inputs['Mode'].default_value = 'POLY'
        fillet_curve.inputs['Radius'].default_value = 0.1
        fillet_curve.inputs['Count'].default_value = 5

        # 6. Curve to Mesh Node
        curve_to_mesh = nodes.new(type='GeometryNodeCurveToMesh')
        curve_to_mesh.location = (0, 200)

        # 7. Curve Circle Node (for profile)
        curve_circle = nodes.new(type='GeometryNodeCurvePrimitiveCircle')
        curve_circle.location = (-600, 0)
        curve_circle.inputs['Radius'].default_value = 0.05
        curve_circle.inputs['Resolution'].default_value = 12

        # 8. Set Material Node
        set_material = nodes.new(type='GeometryNodeSetMaterial')
        set_material.location = (200, 200)
        # Crear o obtener el material "Plástico"
        plastic_mat = bpy.data.materials.get("Plástico")
        if not plastic_mat:
            plastic_mat = bpy.data.materials.new(name="Plástico")
            plastic_mat.diffuse_color = (0.8, 0.1, 0.1, 1)  # Rojo plástico por defecto
        set_material.inputs['Material'].default_value = plastic_mat

        # 9. Instance on Points Node
        instance_on_points = nodes.new(type='GeometryNodeInstanceOnPoints')
        instance_on_points.location = (400, 100)

        # 10. Object Info Node for the nozzle (boquilla)
        object_info_nozzle = nodes.new(type='GeometryNodeObjectInfo')
        object_info_nozzle.location = (600, 100)
        nozzle_obj = bpy.data.objects.get("Boquilla")
        if not nozzle_obj:
            self.report({'ERROR'}, "Objeto 'Boquilla' no encontrado. Crea y nombra un objeto como 'Boquilla'.")
            return {'CANCELLED'}
        object_info_nozzle.inputs['Object'].default_value = nozzle_obj

        # 11. Translate Instances Node
        translate_instances = nodes.new(type='GeometryNodeTranslateInstances')
        translate_instances.location = (800, 100)
        translate_instances.inputs['Translation'].default_value = (0, 0, 0.1)  # Ajusta según sea necesario

        # 12. Join Geometry Node
        join_geometry = nodes.new(type='GeometryNodeJoinGeometry')
        join_geometry.location = (600, 200)

        # Conectar nodos
        links.new(object_info.outputs['Geometry'], resample_curve.inputs['Curve'])
        links.new(resample_curve.outputs['Curve'], trim_curve.inputs['Curve'])
        links.new(value_node.outputs['Value'], trim_curve.inputs['End'])
        links.new(trim_curve.outputs['Curve'], fillet_curve.inputs['Curve'])
        links.new(fillet_curve.outputs['Curve'], curve_to_mesh.inputs['Curve'])
        links.new(curve_circle.outputs['Curve'], curve_to_mesh.inputs['Profile Curve'])
        links.new(curve_to_mesh.outputs['Mesh'], set_material.inputs['Geometry'])
        links.new(set_material.outputs['Geometry'], join_geometry.inputs['Geometry'])

        # Instance on Points
        links.new(trim_curve.outputs['Curve'], instance_on_points.inputs['Points'])
        links.new(object_info_nozzle.outputs['Geometry'], instance_on_points.inputs['Instance'])
        links.new(instance_on_points.outputs['Instances'], translate_instances.inputs['Instances'])
        links.new(translate_instances.outputs['Instances'], join_geometry.inputs['Geometry'])

        # Conectar Join Geometry al Output
        links.new(join_geometry.outputs['Geometry'], group_output.inputs['Geometry'])

        self.report({'INFO'}, "Geometry Nodes generados correctamente.")
        return {'FINISHED'}

# Operador para Animar el Filamento
class WM_OT_animate_filament(Operator):
    """Animar el filamento siguiendo la curva del G-code"""
    bl_idname = "wm.animate_filament"
    bl_label = "Animar Filamento"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        settings = context.scene.gcode_importer_settings

        # Obtener la curva creada
        curve_objs = [obj for obj in bpy.context.scene.objects if obj.type == 'CURVE' and obj.name.startswith("GCode")]
        if not curve_objs:
            self.report({'ERROR'}, "No se encontró ninguna curva. Importa un archivo G-code primero.")
            return {'CANCELLED'}
        curve_obj = curve_objs[-1]  # Seleccionar la última curva importada

        # Obtener el objeto del filamento
        filament = bpy.data.objects.get("Filamento")
        if not filament:
            self.report({'ERROR'}, "Objeto 'Filamento' no encontrado. Genera Geometry Nodes primero.")
            return {'CANCELLED'}

        # Añadir el constraint Follow Path
        follow_path = filament.constraints.new(type='FOLLOW_PATH')
        follow_path.target = curve_obj
        follow_path.use_curve_follow = True

        # Animar el factor de evaluación del constraint
        follow_path.offset_factor = 0.0
        follow_path.keyframe_insert(data_path="offset_factor", frame=1)
        follow_path.offset_factor = 1.0
        follow_path.keyframe_insert(data_path="offset_factor", frame=250)

        # Configurar la línea de tiempo
        bpy.context.scene.frame_start = 1
        bpy.context.scene.frame_end = 250

        self.report({'INFO'}, "Animación del filamento configurada correctamente.")
        return {'FINISHED'}

# Función para importar G-code y crear la animación
def import_gcode(context, filepath):
    print("Ejecutando importación de G-code...")

    scene = context.scene
    mytool = scene.gcode_importer_settings
    import time
    then = time.time()

    parse = parser.GcodeParser()
    model = parse.parseFile(filepath)
    
    if mytool.subdivide:
        model.subdivide_segments(mytool.max_segment_size)
    model.classifySegments()
    
    if mytool.create_continuous:
        curve_obj = model.create_continuous_curve(mytool)
    else:
        model.create_split_layers()
    
    if mytool.create_continuous:
        # Crear el objeto del filamento
        filament = model.create_filament_object(mytool)
        
        # Opcional: Configurar Geometry Nodes aquí si deseas integrarlo en la importación
        # model.setup_geometry_nodes(filament, curve_obj, mytool)
    
    now = time.time()
    print("Importación completada en", now - then, "segundos.")

    return {'FINISHED'}

# Registro de clases
classes = (
    ImportGcodeSettings,
    OBJECT_PT_CustomPanel,
    WM_OT_gcode_import,
    WM_OT_generate_geometry_nodes,
    WM_OT_animate_filament,
)

def register():
    from bpy.utils import register_class
    for cls in classes:
        register_class(cls)
    bpy.types.Scene.gcode_importer_settings = PointerProperty(type=ImportGcodeSettings)

def unregister():
    from bpy.utils import unregister_class
    for cls in reversed(classes):
        unregister_class(cls)
    del bpy.types.Scene.gcode_importer_settings

if __name__ == "__main__":
    register()
