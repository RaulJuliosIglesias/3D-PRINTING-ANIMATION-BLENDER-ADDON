import bpy

#initialize geometry_nodes node group
def geometry_nodes_node_group():
    geometry_nodes = bpy.data.node_groups.new(type = 'GeometryNodeTree', name = "Geometry Nodes")

    geometry_nodes.color_tag = 'NONE'
    geometry_nodes.description = ""

    geometry_nodes.is_modifier = True
    
    #geometry_nodes interface
    #Socket Geometry
    geometry_socket = geometry_nodes.interface.new_socket(name = "Geometry", in_out='OUTPUT', socket_type = 'NodeSocketGeometry')
    geometry_socket.attribute_domain = 'POINT'
    
    #Socket Geometry
    geometry_socket_1 = geometry_nodes.interface.new_socket(name = "Geometry", in_out='INPUT', socket_type = 'NodeSocketGeometry')
    geometry_socket_1.attribute_domain = 'POINT'
    
    
    #initialize geometry_nodes nodes
    #node Group Input.001
    group_input_001 = geometry_nodes.nodes.new("NodeGroupInput")
    group_input_001.name = "Group Input.001"
    
    #node Group Output.001
    group_output_001 = geometry_nodes.nodes.new("NodeGroupOutput")
    group_output_001.name = "Group Output.001"
    group_output_001.is_active_output = True
    
    #node Trim Curve
    trim_curve = geometry_nodes.nodes.new("GeometryNodeTrimCurve")
    trim_curve.name = "Trim Curve"
    trim_curve.mode = 'FACTOR'
    #Selection
    trim_curve.inputs[1].default_value = True
    #Start
    trim_curve.inputs[2].default_value = 0.0
    #End
    trim_curve.inputs[3].default_value = 1.0
    
    #node Curve to Mesh
    curve_to_mesh = geometry_nodes.nodes.new("GeometryNodeCurveToMesh")
    curve_to_mesh.name = "Curve to Mesh"
    #Fill Caps
    curve_to_mesh.inputs[2].default_value = False
    
    #node Curve Circle
    curve_circle = geometry_nodes.nodes.new("GeometryNodeCurvePrimitiveCircle")
    curve_circle.name = "Curve Circle"
    curve_circle.mode = 'RADIUS'
    #Resolution
    curve_circle.inputs[0].default_value = 32
    #Radius
    curve_circle.inputs[4].default_value = 0.05000000074505806
    
    
    
    #Set locations
    group_input_001.location = (-84.36721801757812, -58.384765625)
    group_output_001.location = (915.6328125, -58.384765625)
    trim_curve.location = (165.63278198242188, -58.384765625)
    curve_to_mesh.location = (415.6327819824219, -58.384765625)
    curve_circle.location = (165.63278198242188, -258.384765625)
    
    #Set dimensions
    group_input_001.width, group_input_001.height = 140.0, 100.0
    group_output_001.width, group_output_001.height = 140.0, 100.0
    trim_curve.width, trim_curve.height = 140.0, 100.0
    curve_to_mesh.width, curve_to_mesh.height = 140.0, 100.0
    curve_circle.width, curve_circle.height = 140.0, 100.0
    
    #initialize geometry_nodes links
    #trim_curve.Curve -> curve_to_mesh.Curve
    geometry_nodes.links.new(trim_curve.outputs[0], curve_to_mesh.inputs[0])
    #curve_circle.Curve -> curve_to_mesh.Profile Curve
    geometry_nodes.links.new(curve_circle.outputs[0], curve_to_mesh.inputs[1])
    #group_input_001.Geometry -> trim_curve.Curve
    geometry_nodes.links.new(group_input_001.outputs[0], trim_curve.inputs[0])
    #curve_to_mesh.Mesh -> group_output_001.Geometry
    geometry_nodes.links.new(curve_to_mesh.outputs[0], group_output_001.inputs[0])
    return geometry_nodes

# Create and assign the geometry nodes to the active object
geometry_nodes = geometry_nodes_node_group()
name = bpy.context.object.name
obj = bpy.data.objects[name]
mod = obj.modifiers.new(name="Geometry Nodes", type='NODES')
mod.node_group = geometry_nodes
