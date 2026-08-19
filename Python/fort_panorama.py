"""Bakes a cubemap into the equirectangular panorama MobFort reflects.

    Fort -> Panorama From Cubemap, with cubes selected in the content browser.

or by hand:

    import fort_panorama
    fort_panorama.convert_selected()
    fort_panorama.convert('/Game/Path/To/HDRI_Cube')

A sky sphere reflects a cube and MobFort reflects a long/lat 2D, so this makes the second from the
first rather than asking anyone to keep two imports of one image in step. An .hdr lands as a cube
whatever the import settings say, which is why this goes through the asset and not the file.

Baked through a material that samples the cube, rather than by reading the source image, so the
direction convention is the engine's own on both sides. A panorama built from the file instead
would be a guess at where the seam sits, and a guess that is wrong is a yaw offset in every
reflection with nothing on screen to say so.

The layout is the exact inverse of FortPanoramaUV in MobFortShading.ush. If that function ever
changes, PANORAMA_DIRECTION here changes with it or every reflection turns.
"""

import math
import unreal

MEL = unreal.MaterialEditingLibrary
EAL = unreal.EditorAssetLibrary
KRL = unreal.RenderingLibrary

BAKE_MATERIAL = '/MobFort/Tools/M_FortPanoramaBake'
CUBE_PARAM = 'Cube'

# Panoramas land beside the cube they came from unless a caller says otherwise, so a project keeps
# its skies wherever it already keeps them.
OUTPUT_SUBFOLDER = 'Panorama'
OUTPUT_PREFIX = 'T_Pano_'

# Twice as wide as tall, because a long/lat image is a full turn across and a half turn down.
DEFAULT_WIDTH = 2048

# How small the smallest useful mip is. MaxMip is the mip a roughness of 1 reads, and past a few
# pixels across there is nothing left to blur.
SMALLEST_MIP_PIXELS = 8

# The inverse of FortPanoramaUV: a long/lat coordinate back to the direction it stood for.
PANORAMA_DIRECTION = """
const float Phi = (UV.x - 0.5f) * 2.0f * PI;
const float Theta = UV.y * PI;
const float S = sin(Theta);
return float3(S * cos(Phi), S * sin(Phi), cos(Theta));
"""


def _log(msg):
    unreal.log('[Panorama] ' + str(msg))


def _tools():
    return unreal.AssetToolsHelpers.get_asset_tools()


def _world():
    return unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()


def _split(path):
    package, _, name = path.rpartition('/')
    return package, name


def _sampler_type(texture):
    """What a texture has to be sampled as. An HDR panorama is linear and nothing decodes it."""
    if texture.get_editor_property('srgb'):
        return unreal.MaterialSamplerType.SAMPLERTYPE_COLOR
    return unreal.MaterialSamplerType.SAMPLERTYPE_LINEAR_COLOR


def build_bake_material(default_cube):
    """The material that reads a cube and writes it out flat. Built once and reused.

    A cube is handed in because a texture parameter's sampler type is checked against the texture
    sitting on it as a default, not against whatever an instance later sets. Left on the engine's
    own default cube the material does not compile, and a material that does not compile draws the
    grey default without complaining, so every panorama comes out the same flat colour.
    """
    if EAL.does_asset_exist(BAKE_MATERIAL):
        return unreal.load_asset(BAKE_MATERIAL)

    package, name = _split(BAKE_MATERIAL)
    mat = _tools().create_asset(name, package, unreal.Material, unreal.MaterialFactoryNew())

    # A canvas draw, so the domain is UI. Nothing here is lit and nothing here is blended.
    mat.set_editor_property('material_domain', unreal.MaterialDomain.MD_UI)
    mat.set_editor_property('blend_mode', unreal.BlendMode.BLEND_OPAQUE)

    uv = MEL.create_material_expression(mat, unreal.MaterialExpressionTextureCoordinate, -900, 0)

    direction = MEL.create_material_expression(mat, unreal.MaterialExpressionCustom, -650, 0)
    direction.set_editor_property('code', PANORAMA_DIRECTION)
    direction.set_editor_property('output_type', unreal.CustomMaterialOutputType.CMOT_FLOAT3)
    direction.set_editor_property('description', 'PanoramaDirection')
    uv_input = unreal.CustomInput()
    uv_input.set_editor_property('input_name', 'UV')
    direction.set_editor_property('inputs', [uv_input])

    sample = MEL.create_material_expression(
        mat, unreal.MaterialExpressionTextureSampleParameterCube, -350, 0)
    sample.set_editor_property('parameter_name', CUBE_PARAM)
    sample.set_editor_property('texture', default_cube)
    sample.set_editor_property('sampler_type', _sampler_type(default_cube))

    MEL.connect_material_expressions(uv, '', direction, 'UV')
    MEL.connect_material_expressions(direction, '', sample, 'UVs')
    MEL.connect_material_property(sample, 'RGB', unreal.MaterialProperty.MP_EMISSIVE_COLOR)

    errors = MEL.recompile_material(mat)
    for error in errors:
        unreal.log_warning('[Panorama] %s: %s' % (name, error))

    EAL.save_loaded_asset(mat, only_if_is_dirty=False)
    _log('built ' + BAKE_MATERIAL)
    return mat


def _bake_target(width, height):
    """The render target the cube is drawn into.

    Transient, and linear half float because the source is HDR. Where the panorama lands is decided
    by the full path handed to the static texture call, so this never needs to be an
    asset and never leaves one behind.
    """
    return KRL.create_render_target2d(_world(), width, height,
                                      unreal.TextureRenderTargetFormat.RTF_RGBA16F,
                                      unreal.LinearColor(0.0, 0.0, 0.0, 1.0), True)


def max_mip(width):
    """The mip a roughness of 1 should read, for a panorama this wide."""
    return max(0.0, math.log(max(width, 1) / float(SMALLEST_MIP_PIXELS), 2.0))


def convert(cube_path, output_path=None, width=DEFAULT_WIDTH):
    """Writes one cube out as a panorama. Returns the texture, or None.

    Rebuilt rather than edited in place, because the resolution can change and a stale mip chain is
    a reflection that is sharp where it should not be with nothing to say why.
    """
    cube = unreal.load_asset(cube_path)
    if not isinstance(cube, unreal.TextureCube):
        unreal.log_warning('[Panorama] %s is not a TextureCube' % cube_path)
        return None

    if output_path is None:
        folder, _ = _split(cube_path)
        output_path = '%s/%s/%s%s' % (folder, OUTPUT_SUBFOLDER, OUTPUT_PREFIX, cube.get_name())

    height = max(width // 2, 1)

    material = build_bake_material(cube)
    instance = unreal.MaterialLibrary.create_dynamic_material_instance(_world(), material)
    instance.set_texture_parameter_value(CUBE_PARAM, cube)

    render_target = _bake_target(width, height)
    KRL.draw_material_to_render_target(_world(), render_target, instance)

    # CreateUniqueAssetName is what names the result, so anything already sitting on the path would
    # push this one to a _1 nobody is pointing at.
    if EAL.does_asset_exist(output_path):
        EAL.delete_asset(output_path)

    texture = KRL.render_target_create_static_texture2d_editor_only(
        render_target, output_path,
        unreal.TextureCompressionSettings.TC_HDR,
        unreal.TextureMipGenSettings.TMGS_SIMPLE_AVERAGE)

    if texture is None:
        unreal.log_warning('[Panorama] %s produced nothing' % cube_path)
        return None

    # Roughness picks a mip, so the chain is the whole feature. Simple average rather than the
    # angular filter, which is a cubemap convolution and means nothing applied to a flat image.
    texture.set_editor_property('srgb', False)
    texture.set_editor_property('compression_settings', unreal.TextureCompressionSettings.TC_HDR)
    texture.set_editor_property('mip_gen_settings', unreal.TextureMipGenSettings.TMGS_SIMPLE_AVERAGE)
    texture.set_editor_property('lod_group', unreal.TextureGroup.TEXTUREGROUP_WORLD)

    # Longitude wraps and latitude does not, so the seam down the back of the image closes and the
    # poles stay where they are.
    texture.set_editor_property('address_x', unreal.TextureAddress.TA_WRAP)
    texture.set_editor_property('address_y', unreal.TextureAddress.TA_CLAMP)

    EAL.save_loaded_asset(texture, only_if_is_dirty=False)

    _log('%s -> %s (%dx%d, MaxMip %.1f)'
         % (cube.get_name(), output_path, width, height, max_mip(width)))
    return texture


def apply_to_instances(texture, instance_paths, width=DEFAULT_WIDTH):
    """Points material instances at a panorama and tells them how long its mip chain is."""
    for path in instance_paths:
        instance = unreal.load_asset(path)
        if not isinstance(instance, unreal.MaterialInstanceConstant):
            unreal.log_warning('[Panorama] %s is not a material instance' % path)
            continue

        MEL.set_material_instance_texture_parameter_value(instance, 'SpecPanorama', texture)
        MEL.set_material_instance_scalar_parameter_value(instance, 'MaxMip', max_mip(width))
        EAL.save_loaded_asset(instance, only_if_is_dirty=False)
        _log('pointed %s at %s' % (instance.get_name(), texture.get_name()))


def find_cubes(root):
    """Every TextureCube under a folder, skipping anything already written out."""
    found = []
    for path in EAL.list_assets(root, recursive=True, include_folder=False):
        path = path.split('.')[0]
        if ('/%s/' % OUTPUT_SUBFOLDER) in path:
            continue
        if isinstance(unreal.load_asset(path), unreal.TextureCube):
            found.append(path)
    return found


def convert_all(root, width=DEFAULT_WIDTH):
    """Every cube under a folder, written out as panoramas beside it."""
    return _convert_each(find_cubes(root), width)


def convert_selected(width=DEFAULT_WIDTH):
    """Every cube selected in the content browser. What the menu item calls."""
    selected = unreal.EditorUtilityLibrary.get_selected_assets()
    cubes = [a.get_path_name().split('.')[0] for a in selected
             if isinstance(a, unreal.TextureCube)]

    if not cubes:
        unreal.log_warning('[Panorama] select one or more TextureCube assets first')
        return []

    return _convert_each(cubes, width)


def _convert_each(cube_paths, width):
    made = []
    for cube_path in cube_paths:
        texture = convert(cube_path, width=width)
        if texture:
            made.append(texture)

    _log('%d panorama(s). MaxMip for this width is %.1f - set it on the instance, or on the sky '
         'that names the panorama.' % (len(made), max_mip(width)))
    return made
