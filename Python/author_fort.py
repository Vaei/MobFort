"""Authors the MobFort gradient atlas, lighting collection, material functions and masters.

Run from the editor's Python console:

    import sys, importlib
    sys.path.append('<PluginDir>/Python')
    import author_fort
    importlib.reload(author_fort)
    author_fort.build_all()

Every phase is idempotent: an existing asset is emptied and rebuilt in place, so material instances
keep their references and their overrides.

The maths lives in Shaders/Public/MobFortShading.ush and is reached from Custom nodes through the
/MobFort mapping the runtime module registers, so the graphs here stay thin. What remains in a
graph is what cannot leave one: material parameters, texture objects, static switches, and the
vertex and primitive attributes a Custom node has no honest way to reach.

Feature gating is static bools on material function inputs rather than switches in the master. A
discarded function input is never compiled, so a feature that is off takes its texture samples and
its maths with it.
"""

import importlib

import unreal

import fort_version

MEL = unreal.MaterialEditingLibrary
EAL = unreal.EditorAssetLibrary

ROOT = '/MobFort'
FN_ROOT = ROOT + '/Functions'
TEX_ROOT = ROOT + '/Textures'
GRAD_ROOT = ROOT + '/Gradients'
INST_ROOT = ROOT + '/Instances'

INCLUDES = ['/MobFort/Public/MobFortShading.ush']

GRADIENT_ASSET = GRAD_ROOT + '/GA_FortCharacter'
# The atlas the Gradient asset bakes itself into. Exposed as a texture parameter so a project can
# point a character at its own atlas without touching this plugin's content.
GRADIENT_TEXTURE = GRAD_ROOT + '/T_GA_FortCharacter'
LIGHTING_MPC = ROOT + '/MPC_FortLighting'

# Placeholders have to match the sampler type they stand in for or the material will not compile.
# Copied into plugin content rather than referenced where they were found, so the plugin carries
# its own defaults and drops into a project that has no /Game/Tools. T_BaseCRM is not in that list
# because it ships with the plugin already.
BASE_TEXTURES = [
    ('T_BaseWhite', '/Game/Tools/BaseTextures/T_BaseWhite'),
    ('T_BaseNormal', '/Game/Tools/BaseTextures/T_BaseNormal'),
    ('T_BaseHDRI', '/Game/Tools/BaseTextures/T_BaseHDRI'),
]

TEX_ALBEDO = TEX_ROOT + '/T_BaseWhite'
TEX_NORMAL = TEX_ROOT + '/T_BaseNormal'
TEX_CRM = TEX_ROOT + '/T_BaseCRM'
TEX_PANORAMA = TEX_ROOT + '/T_BaseHDRI'

FIT = unreal.FunctionInputType
CMOT = unreal.CustomMaterialOutputType
ST = unreal.MaterialSamplerType
MP = unreal.MaterialProperty
LC = unreal.LinearColor

GROUP_FEATURES = '00 - Features'
GROUP_TEXTURES = '10 - Textures'
GROUP_GRADIENT = '15 - Gradient'
GROUP_SURFACE = '20 - Surface'
GROUP_SPECULAR = '30 - Specular'
GROUP_DIFFUSE = '40 - Diffuse'
GROUP_WET = '45 - Wetness'
GROUP_TEAM = '50 - Team'
GROUP_SKIN = '60 - Skin'
GROUP_DEBUG = '90 - Debug'


def _log(msg):
    unreal.log('[MobFort] ' + str(msg))


def _tools():
    return unreal.AssetToolsHelpers.get_asset_tools()


# ---------------------------------------------------------------------------
# Asset plumbing
# ---------------------------------------------------------------------------

def _clear_function(fn):
    """Empties a MaterialFunction.

    delete_all_material_expressions_in_function leaves nodes behind, so re-running a builder
    silently accumulates duplicates and the caller's connections then land on whichever copy the
    name lookup hits first. Loop until the graph is actually empty.
    """
    for _ in range(16):
        exprs = MEL.get_material_function_expressions(fn)
        if not exprs:
            return
        for e in exprs:
            MEL.delete_material_expression_in_function(fn, e)
    raise RuntimeError('could not empty material function %s' % fn.get_name())


def _clear_material(mat):
    """Empties a Material. Same caveat as _clear_function."""
    for _ in range(16):
        exprs = MEL.get_material_expressions(mat)
        if not exprs:
            return
        for e in exprs:
            MEL.delete_material_expression(mat, e)
    raise RuntimeError('could not empty material %s' % mat.get_name())


def get_or_create_function(name, description=''):
    path = FN_ROOT + '/' + name
    if EAL.does_asset_exist(path):
        fn = unreal.load_asset(path)
        _clear_function(fn)
    else:
        fn = _tools().create_asset(name, FN_ROOT, unreal.MaterialFunction,
                                   unreal.MaterialFunctionFactoryNew())
    fn.set_editor_property('description', description)
    fn.set_editor_property('expose_to_library', True)
    fn.set_editor_property('library_categories_text', ['MobFort'])
    return fn


def get_or_create_material(name):
    path = ROOT + '/' + name
    if EAL.does_asset_exist(path):
        mat = unreal.load_asset(path)
        _clear_material(mat)
    else:
        mat = _tools().create_asset(name, ROOT, unreal.Material, unreal.MaterialFactoryNew())
    return mat


def save(asset):
    fort_version.stamp(asset)
    EAL.save_loaded_asset(asset, only_if_is_dirty=False)


# ---------------------------------------------------------------------------
# Expression helpers
# ---------------------------------------------------------------------------

# Nodes are authored on a loose grid for readability in this script. Material nodes are far wider
# than they are tall, so authored columns sit closer together than the nodes in them really are.
# The graph is relaid out once built: distinct x positions become evenly spaced columns, which
# keeps the left-to-right order and guarantees nothing overlaps.
COLUMN_PITCH = 460


def _is_fn(owner):
    return isinstance(owner, unreal.MaterialFunction)


def expr(owner, cls, x, y):
    if _is_fn(owner):
        return MEL.create_material_expression_in_function(owner, cls, int(x), int(y))
    return MEL.create_material_expression(owner, cls, int(x), int(y))


def link(src, src_out, dst, dst_in):
    if not MEL.connect_material_expressions(src, src_out, dst, dst_in):
        raise RuntimeError('failed to connect %s.%s -> %s.%s'
                           % (src.get_name(), src_out or '<default>',
                              dst.get_name(), dst_in or '<default>'))


def _spread(exprs):
    columns = sorted({e.get_editor_property('material_expression_editor_x') for e in exprs})
    count = len(columns)
    # Left of the origin: the output node sits at zero and cannot be moved, so numbering columns
    # from zero upwards would put the whole graph to the right of what it feeds.
    placement = {x: (i - count) * COLUMN_PITCH for i, x in enumerate(columns)}
    for e in exprs:
        e.set_editor_property('material_expression_editor_x',
                              placement[e.get_editor_property('material_expression_editor_x')])


def _vec4(x, y, z, w):
    """PreviewValue is an FVector4f, whose Python binding takes no constructor arguments."""
    v = unreal.Vector4f()
    v.set_editor_property('x', float(x))
    v.set_editor_property('y', float(y))
    v.set_editor_property('z', float(z))
    v.set_editor_property('w', float(w))
    return v


def fn_input(fn, name, input_type, x, y, sort, default=None, description=''):
    e = expr(fn, unreal.MaterialExpressionFunctionInput, x, y)
    e.set_editor_property('input_name', name)
    e.set_editor_property('input_type', input_type)
    e.set_editor_property('sort_priority', sort)
    e.set_editor_property('description', description)
    if default is not None:
        if isinstance(default, (int, float)):
            default = (float(default), 0.0, 0.0, 0.0)
        default = tuple(default) + (0.0,) * (4 - len(default))
        e.set_editor_property('preview_value', _vec4(*default[:4]))
        e.set_editor_property('use_preview_value_as_default', True)
    return e


def fn_output(fn, name, x, y, sort):
    e = expr(fn, unreal.MaterialExpressionFunctionOutput, x, y)
    e.set_editor_property('output_name', name)
    e.set_editor_property('sort_priority', sort)
    return e


def custom(owner, code, output_type, input_names, extra_outputs, x, y, description=''):
    e = expr(owner, unreal.MaterialExpressionCustom, x, y)
    e.set_editor_property('code', code)
    e.set_editor_property('output_type', output_type)
    e.set_editor_property('description', description)
    # FCustomInput/FCustomOutput are plain USTRUCTs, so they take no constructor kwargs.
    ins = []
    for n in input_names:
        s = unreal.CustomInput()
        s.set_editor_property('input_name', n)
        ins.append(s)
    outs = []
    for n, t in extra_outputs:
        s = unreal.CustomOutput()
        s.set_editor_property('output_name', n)
        s.set_editor_property('output_type', t)
        outs.append(s)
    e.set_editor_property('inputs', ins)
    e.set_editor_property('additional_outputs', outs)
    e.set_editor_property('include_file_paths', INCLUDES)
    return e


def const(owner, value, x, y):
    e = expr(owner, unreal.MaterialExpressionConstant, x, y)
    e.set_editor_property('r', float(value))
    return e


def const3(owner, rgb, x, y):
    e = expr(owner, unreal.MaterialExpressionConstant3Vector, x, y)
    e.set_editor_property('constant', LC(rgb[0], rgb[1], rgb[2], 1.0))
    return e


def scalar_param(owner, name, default, group, x, y, sort=0, desc=None):
    e = expr(owner, unreal.MaterialExpressionScalarParameter, x, y)
    e.set_editor_property('parameter_name', name)
    e.set_editor_property('default_value', float(default))
    e.set_editor_property('group', group)
    e.set_editor_property('sort_priority', sort)
    if desc:
        e.set_editor_property('desc', desc)
    return e


def cpd_scalar(owner, name, index, x, y, desc=None):
    """A scalar read from the primitive's custom primitive data rather than from an instance.

    The index is the parameter: a CPD parameter never appears on an instance, so the name is only
    what the graph calls it and the default is whatever the primitive has not written, which is
    zero. MobFortTypes.h holds the indices these have to agree with.
    """
    e = expr(owner, unreal.MaterialExpressionScalarParameter, x, y)
    e.set_editor_property('parameter_name', name)
    e.set_editor_property('default_value', 0.0)
    e.set_editor_property('use_custom_primitive_data', True)
    e.set_editor_property('primitive_data_index', int(index))
    if desc:
        e.set_editor_property('desc', desc)
    return e


def vector_param(owner, name, rgba, group, x, y, sort=0, desc=None):
    e = expr(owner, unreal.MaterialExpressionVectorParameter, x, y)
    e.set_editor_property('parameter_name', name)
    e.set_editor_property('default_value', LC(*rgba))
    e.set_editor_property('group', group)
    e.set_editor_property('sort_priority', sort)
    if desc:
        e.set_editor_property('desc', desc)
    return e


def texture_sample_param(owner, name, texture_path, sampler_type, group, x, y, sort=0):
    e = expr(owner, unreal.MaterialExpressionTextureSampleParameter2D, x, y)
    e.set_editor_property('parameter_name', name)
    e.set_editor_property('texture', unreal.load_asset(texture_path))
    e.set_editor_property('sampler_type', sampler_type)
    # Shared:Wrap collapses every 2D tap in the material onto one sampler state, which is what
    # keeps the character master well inside the sampler limit at ES3.1.
    e.set_editor_property('sampler_source', unreal.SamplerSourceMode.SSM_WRAP_WORLD_GROUP_SETTINGS)
    e.set_editor_property('group', group)
    e.set_editor_property('sort_priority', sort)
    return e


def texture_object_param(owner, name, texture_path, sampler_type, group, x, y, sort=0):
    e = expr(owner, unreal.MaterialExpressionTextureObjectParameter, x, y)
    e.set_editor_property('parameter_name', name)
    e.set_editor_property('texture', unreal.load_asset(texture_path))
    e.set_editor_property('sampler_type', sampler_type)
    e.set_editor_property('group', group)
    e.set_editor_property('sort_priority', sort)
    return e


def bool_param(owner, name, default, group, x, y, sort=0, desc=None):
    e = expr(owner, unreal.MaterialExpressionStaticBoolParameter, x, y)
    e.set_editor_property('parameter_name', name)
    e.set_editor_property('default_value', bool(default))
    e.set_editor_property('group', group)
    e.set_editor_property('sort_priority', sort)
    if desc:
        e.set_editor_property('desc', desc)
    return e


def switch_param(owner, name, true_src, true_out, false_src, false_out, group, x, y,
                 default=False, sort=0, desc=None):
    """A StaticSwitchParameter, which is itself the switch rather than a bool feeding one."""
    sw = expr(owner, unreal.MaterialExpressionStaticSwitchParameter, x, y)
    sw.set_editor_property('parameter_name', name)
    sw.set_editor_property('default_value', bool(default))
    sw.set_editor_property('group', group)
    sw.set_editor_property('sort_priority', sort)
    if desc:
        sw.set_editor_property('desc', desc)
    link(true_src, true_out, sw, 'True')
    link(false_src, false_out, sw, 'False')
    return sw


def switch(owner, value_src, value_out, true_src, true_out, false_src, false_out, x, y):
    """A plain StaticSwitch, driven by a static bool that came from somewhere else."""
    sw = expr(owner, unreal.MaterialExpressionStaticSwitch, x, y)
    link(true_src, true_out, sw, 'True')
    link(false_src, false_out, sw, 'False')
    link(value_src, value_out, sw, 'Value')
    return sw


def mul(owner, a, ao, b, bo, x, y):
    e = expr(owner, unreal.MaterialExpressionMultiply, x, y)
    link(a, ao, e, 'A')
    link(b, bo, e, 'B')
    return e


def add(owner, a, ao, b, bo, x, y):
    e = expr(owner, unreal.MaterialExpressionAdd, x, y)
    link(a, ao, e, 'A')
    link(b, bo, e, 'B')
    return e


def lerp(owner, a, ao, b, bo, t, to, x, y):
    e = expr(owner, unreal.MaterialExpressionLinearInterpolate, x, y)
    link(a, ao, e, 'A')
    link(b, bo, e, 'B')
    link(t, to, e, 'Alpha')
    return e


def append(owner, a, ao, b, bo, x, y):
    e = expr(owner, unreal.MaterialExpressionAppendVector, x, y)
    link(a, ao, e, 'A')
    link(b, bo, e, 'B')
    return e


def mask(owner, src, src_out, x, y, r=False, g=False, b=False, a=False):
    e = expr(owner, unreal.MaterialExpressionComponentMask, x, y)
    e.set_editor_property('r', r)
    e.set_editor_property('g', g)
    e.set_editor_property('b', b)
    e.set_editor_property('a', a)
    link(src, src_out, e, '')
    return e


def collection(owner, name, x, y):
    e = expr(owner, unreal.MaterialExpressionCollectionParameter, x, y)
    e.set_editor_property('collection', unreal.load_asset(LIGHTING_MPC))
    e.set_editor_property('parameter_name', name)
    return e


def gradient_atlas_param(owner, x, y):
    """The Atlas pin, as a texture parameter, so an instance can swap atlases per character.

    Linear Color because the bake is always uncompressed and non-sRGB, whatever format the
    Gradient asset was set to.
    """
    return texture_object_param(owner, 'Atlas', GRADIENT_TEXTURE, ST.SAMPLERTYPE_LINEAR_COLOR,
                                GROUP_GRADIENT, x, y, 0)


def gradient_row_param(owner, name, row_name, x, y, sort):
    """The Row pin, as a scalar parameter.

    Row is resolved from the gradient name at compile time when this is left unconnected, which
    bakes the plugin's own layout into the shader. Driving it from a parameter instead means a
    project atlas only has to say where its rows are, not match an order it did not choose.
    """
    index = [n for n, _ in GRADIENT_ROWS].index(row_name)
    return scalar_param(owner, name, float(index), GROUP_GRADIENT, x, y, sort,
                        'Row in the atlas. Whole numbers only: a fraction lands between two rows '
                        'and the filter blends them. Default is "%s".' % row_name)


def sample_gradient(owner, row_name, time_src, time_out, atlas, row, x, y):
    e = expr(owner, unreal.MaterialExpressionSampleGradient, x, y)
    # Both are overridden by the pins below. Kept so the node still names its row in the graph,
    # and so the material has a hard reference to the asset it was authored against.
    e.set_editor_property('gradient', unreal.load_asset(GRADIENT_ASSET))
    e.set_editor_property('gradient_name', row_name)
    link(time_src, time_out, e, 'Time')
    link(atlas, '', e, 'Atlas')
    link(row, '', e, 'Row')
    return e


def fn_call(owner, function_name, x, y):
    e = expr(owner, unreal.MaterialExpressionMaterialFunctionCall, x, y)
    e.set_editor_property('material_function', unreal.load_asset(FN_ROOT + '/' + function_name))
    return e


def finish_function(fn):
    _spread(MEL.get_material_function_expressions(fn))
    MEL.update_material_function(fn)
    save(fn)


# ---------------------------------------------------------------------------
# Phase 1 - textures
# ---------------------------------------------------------------------------

def build_textures():
    """Copies the placeholder textures into plugin content."""
    for name, source in BASE_TEXTURES:
        dest = TEX_ROOT + '/' + name
        if EAL.does_asset_exist(dest):
            continue
        if not EAL.does_asset_exist(source):
            raise RuntimeError('missing base texture %s' % source)
        if not EAL.duplicate_asset(source, dest):
            raise RuntimeError('could not copy %s to %s' % (source, dest))
        _log('copied ' + dest)

    # Roughness picks a mip, so a panorama with no mip chain is a mirror at every roughness.
    # Simple average is the right filter for an equirectangular image: the engine's angular filter
    # is a cubemap convolution and means nothing applied to one.
    pano = unreal.load_asset(TEX_PANORAMA)
    wanted = unreal.TextureMipGenSettings.TMGS_SIMPLE_AVERAGE
    if pano and pano.get_editor_property('mip_gen_settings') != wanted:
        pano.set_editor_property('mip_gen_settings', wanted)
        save(pano)
        _log('T_BaseHDRI mip generation set to simple average')

    return pano


def panorama_sampler_type():
    pano = unreal.load_asset(TEX_PANORAMA)
    if pano is not None and pano.get_editor_property('srgb'):
        return ST.SAMPLERTYPE_COLOR
    return ST.SAMPLERTYPE_LINEAR_COLOR


# ---------------------------------------------------------------------------
# Phase 2 - gradient atlas
# ---------------------------------------------------------------------------

GI = unreal.GradientInterp
GB = unreal.GradientBlendSpace

# Row order is what a Sample Gradient node resolves a name against, and a material that already
# compiled holds the row it resolved to. Reordering these means recompiling the masters.
#
# Every row blends in OkLab: even lightness ramps, and no muddy midpoint through the red skin
# range that a linear RGB blend would give.
GRADIENT_ROWS = [
    ('DiffuseFalloff', [
        (0.00, (0.10, 0.11, 0.14), GI.LINEAR),
        (0.40, (0.32, 0.33, 0.36), GI.EASE),
        (0.52, (0.78, 0.78, 0.80), GI.EASE),
        (1.00, (1.00, 1.00, 1.00), GI.LINEAR),
    ]),
    ('SkinDiffuseFalloff', [
        (0.00, (0.30, 0.07, 0.05), GI.LINEAR),
        (0.13, (0.42, 0.13, 0.10), GI.LINEAR),
        (0.63, (0.92, 0.86, 0.84), GI.EASE),
        (0.88, (0.97, 0.99, 1.00), GI.LINEAR),
        (1.00, (1.00, 1.00, 1.00), GI.LINEAR),
    ]),
    ('SkinUnderglow', [
        (0.00, (0.00, 0.00, 0.00), GI.LINEAR),
        (0.25, (0.55, 0.12, 0.06), GI.LINEAR),
        (0.55, (0.25, 0.05, 0.03), GI.EASE),
        (1.00, (0.00, 0.00, 0.00), GI.LINEAR),
    ]),
    # The knee sits well before the silhouette. At a near-perfect grazing angle the rim is a
    # sub-pixel band on a character standing side on, which is exactly when it is needed.
    ('FresnelEnemy', [
        (0.00, (0.00, 0.00, 0.00), GI.LINEAR),
        (0.30, (0.00, 0.00, 0.00), GI.LINEAR),
        (0.62, (1.20, 0.06, 0.03), GI.EASE),
        (1.00, (2.00, 0.15, 0.08), GI.LINEAR),
    ]),
    ('FresnelAlly', [
        (0.00, (0.00, 0.00, 0.00), GI.LINEAR),
        (0.35, (0.00, 0.00, 0.00), GI.LINEAR),
        (0.68, (0.18, 0.38, 0.75), GI.EASE),
        (1.00, (0.35, 0.70, 1.20), GI.LINEAR),
    ]),
]


def build_gradients():
    """GA_FortCharacter, five rows of one atlas.

    HDR format because the rim rows run past 1.0 - a rim that can only reach white cannot separate
    a character from a white wall.
    """
    if EAL.does_asset_exist(GRADIENT_ASSET):
        ga = unreal.load_asset(GRADIENT_ASSET)
    else:
        ga = _tools().create_asset('GA_FortCharacter', GRAD_ROOT, unreal.GradientAsset,
                                   unreal.GradientAssetFactory())

    layers = []
    for name, stops in GRADIENT_ROWS:
        layer = unreal.GradientLayer()
        layer.set_editor_property('name', name)
        layer.set_editor_property('blend_space', GB.OK_LAB)
        built = []
        for time, rgb, interp in stops:
            stop = unreal.GradientStop()
            stop.set_editor_property('time', float(time))
            stop.set_editor_property('color', LC(rgb[0], rgb[1], rgb[2], 1.0))
            stop.set_editor_property('interp', interp)
            built.append(stop)
        layer.set_editor_property('stops', built)
        layers.append(layer)

    ga.set_editor_property('width', 256)
    ga.set_editor_property('format', unreal.GradientTextureFormat.HDR)

    # ALWAYS, because the editor module re-bakes off the property change notification and the
    # default notify mode does not raise one for every property.
    ga.set_editor_property('gradients', layers,
                           unreal.PropertyAccessChangeNotifyMode.ALWAYS)
    save(ga)

    tex = ga.get_editor_property('texture')
    if tex is None:
        raise RuntimeError('gradient asset did not bake a texture')
    save(tex)
    _log('gradient atlas baked: %s' % tex.get_name())
    return ga


# ---------------------------------------------------------------------------
# Phase 3 - lighting collection
# ---------------------------------------------------------------------------

# Packed into vectors rather than spread over scalars because every one of these is a node in every
# graph that reads it, and four components cost the same one node as one does.
#
#   SunDirection  xyz toward the light. W is deliberately unused
#   SunColor      rgb, a intensity
#   Indirect      diffuse scale, specular scale, clamp min, clamp max
#   Depth         brighten start, brighten end, brighten max, rim scale max
#
# SunDirection.w carries nothing on purpose. An external tool that writes the light vector will
# write a whole FLinearColor, so anything parked in the fourth component gets clobbered by whatever
# alpha it happened to construct - which is exactly the kind of failure that looks like a tuning
# problem for an hour. Tuning values that are not part of a vector get their own scalar.
MPC_VECTORS = [
    ('SunDirection', (0.35, -0.55, 0.75, 0.0)),
    ('SunColor', (1.0, 0.96, 0.88, 1.0)),
    ('Indirect', (1.0, 1.0, 0.35, 1.5)),
    ('Depth', (500.0, 4000.0, 0.35, 1.5)),
]

MPC_SCALARS = [
    ('SpecDarkenExponent', 1.5),
    # How far round the sky is turned. Written by whatever owns the sky sphere, so the panorama a
    # character reflects and the sky behind them face the same way.
    ('SkyYaw', 0.0),
]

# Vectors nothing here reads, published for whatever else in a project has to line up with the sky.
MPC_EXTRA_VECTORS = [
    # Where the sky projects from, so a material doing its own projection can use the same point.
    ('SkyProjectionCenter', (0.0, 0.0, 0.0, 0.0)),
]


def build_lighting_collection():
    """MPC_FortLighting: the single directional light, written by the level and only read here.

    There is no light actor in this path and no indirect lighting cache to sample, so the two
    Indirect scales are the hook a lighting volume writes instead. Keeping diffuse and specular
    separate is what reproduces specular darkening faster than diffuse as an area gets darker.
    """
    if EAL.does_asset_exist(LIGHTING_MPC):
        mpc = unreal.load_asset(LIGHTING_MPC)
    else:
        mpc = _tools().create_asset('MPC_FortLighting', ROOT,
                                    unreal.MaterialParameterCollection,
                                    unreal.MaterialParameterCollectionFactoryNew())

    vectors = []
    for name, value in MPC_VECTORS + MPC_EXTRA_VECTORS:
        p = unreal.CollectionVectorParameter()
        p.set_editor_property('parameter_name', name)
        p.set_editor_property('default_value', LC(*value))
        vectors.append(p)

    scalars = []
    for name, value in MPC_SCALARS:
        p = unreal.CollectionScalarParameter()
        p.set_editor_property('parameter_name', name)
        p.set_editor_property('default_value', float(value))
        scalars.append(p)

    mpc.set_editor_property('vector_parameters', vectors)
    mpc.set_editor_property('scalar_parameters', scalars)
    save(mpc)
    _log('lighting collection built')
    return mpc


# ---------------------------------------------------------------------------
# Phase 4 - material functions
# ---------------------------------------------------------------------------

_CODE_SURFACE = """
FortUnpackCRM(CRM, Cavity, Roughness, Metallic);

float3 WetNormalTS = NormalTS;
Albedo = AlbedoIn;
Wet = FortWetness(WetMask, WetPooling, WetDarken, WetRoughness, WetFlatten, Cavity,
                  Parameters.TangentToWorld, WetNormalTS, Albedo, Roughness);

float3 N = FortWorldNormal(WetNormalTS, Parameters.TangentToWorld);
float3 L = normalize(SunDirection.xyz);

NdotV = saturate(dot(N, V));
DiffuseTime = FortDiffuseTime(dot(N, L));
R = FortReflect(N, V);

FortIndirect(Indirect, SpecDarken, LightDarken, DiffuseScale, SpecScale);
FortDepth(Depth, DepthParams, Brighten, FresnelScale);

return N;
"""

_CODE_WET_MASK = """
return FortWetMask(LocalPos.z, BoundsMin.z, BoundsMax.z, WetLine, Wetness, Softness);
"""

_CODE_SPECULAR = """
return FortSpecular(Panorama, PanoramaSampler, R, Albedo, Metallic, Roughness, NdotV,
                    SpecularScalar, MaxMip, FresnelBoost, bFresnel, SkyYaw);
"""

_CODE_WEAPON_DIFFUSE = """
return FortSmoothstepDiffuse(DiffuseTime, ShadowEdge, LightEdge, ShadowColor, LightColor);
"""

_CODE_CHARACTER_MASKS = """
Underglow = FortUnderglowMask(NdotV, UnderglowPower, DiffuseScale);
return FortFresnelMask(N, NdotV, LocalPos.z, BoundsMin.z, BoundsMax.z,
                       UpBias, HeightBias, FresnelScale);
"""

_CODE_COMPOSE = """
return FortCompose(Albedo, Diffuse, SunColor, Cavity, DiffuseScale, Specular, SpecScale,
                   Emissive, Extra, Brighten);
"""

_CODE_DEBUG = """
return FortDebugView((int)(Mode + 0.5f), Diffuse, Specular, N, Cavity, Fresnel, SkinMask,
                     Underglow, Brighten, Roughness, Metallic, Wet);
"""


def build_surface_function():
    """MF_FortSurface: the four textures, the shading vectors and the two indirect responses.

    Everything all three masters share, so a master carries one call to this rather than a copy of
    its parameters. Its parameters are the master's parameters: a parameter authored inside a
    material function still appears on an instance of anything that calls it.
    """
    fn = get_or_create_function(
        'MF_FortSurface',
        'Samples the BaseColor, Normal and CRM pack, builds the shading vectors against the '
        'collection sun, and takes the one panorama tap that stands in for every reflection in the '
        'scene. Shared by every MobFort master.')

    pano_type = panorama_sampler_type()

    # --- albedo ------------------------------------------------------------
    base = texture_sample_param(fn, 'BaseColor', TEX_ALBEDO, ST.SAMPLERTYPE_COLOR,
                                GROUP_TEXTURES, 0, 0, 0)
    tint = vector_param(fn, 'Tint', (1, 1, 1, 1), GROUP_SURFACE, 0, 200, 0,
                        'Multiplies BaseColor. Team colour belongs here, not in the rim.')
    albedo = mul(fn, base, 'RGB', tint, '', 200, 100)

    # --- emissive ----------------------------------------------------------
    # The albedo's alpha, so a glowing element needs no texture of its own. A texture with no
    # alpha channel samples as 1, which is why this is off by default: turning it on over an
    # albedo that has no alpha makes the whole surface emit.
    emissive_intensity = scalar_param(fn, 'EmissiveIntensity', 1.0, GROUP_SURFACE, 0, 250, 20)
    emissive_on = mul(fn, base, 'A', emissive_intensity, '', 200, 300)
    emissive = switch_param(fn, 'bEmissive', emissive_on, '', const(fn, 0.0, 200, 350), '',
                            GROUP_FEATURES, 400, 320, default=False, sort=3,
                            desc='Emissive mask from the albedo alpha. An albedo with no alpha '
                                 'channel samples as 1 and the whole surface emits.')

    # --- normal and pack ---------------------------------------------------
    normal = texture_sample_param(fn, 'Normal', TEX_NORMAL, ST.SAMPLERTYPE_NORMAL,
                                  GROUP_TEXTURES, 0, 400, 2)
    # Masks, not Linear Color: the pack is TC_Masks, and the sampler type has to agree with the
    # compression or the material will not compile. It is the branch that is off by default, so
    # nothing else catches a mismatch here.
    crm_tex = texture_sample_param(fn, 'CRM', TEX_CRM, ST.SAMPLERTYPE_MASKS,
                                   GROUP_TEXTURES, 0, 600, 1)

    c_cavity = scalar_param(fn, 'Cavity', 1.0, GROUP_SURFACE, 0, 800, 10,
                            'Micro shadowing. 1 is none.')
    c_rough = scalar_param(fn, 'Roughness', 0.5, GROUP_SURFACE, 0, 900, 11)
    c_metallic = scalar_param(fn, 'Metallic', 0.0, GROUP_SURFACE, 0, 1000, 12)
    packed = append(fn, append(fn, c_cavity, '', c_rough, '', 200, 850), '', c_metallic, '', 400, 900)

    crm = switch_param(fn, 'bUseCRMTexture', crm_tex, 'RGB', packed, '', GROUP_FEATURES,
                       600, 700, default=False, sort=1,
                       desc='Read Cavity, Roughness and Metallic from the texture rather than '
                            'from the three scalars.')

    # --- collection --------------------------------------------------------
    sun_dir = collection(fn, 'SunDirection', 0, 1200)
    spec_darken = collection(fn, 'SpecDarkenExponent', 0, 1250)
    indirect = collection(fn, 'Indirect', 0, 1400)
    depth_params = collection(fn, 'Depth', 0, 1500)

    # Alpha is the sun's intensity, folded in here so the collection's own documentation is true.
    # Not the light actor's lux: an unlit master has no exposure to relate that to, so this stays a
    # hand-set multiplier and Sync Sun leaves it alone.
    sun_col_raw = collection(fn, 'SunColor', 0, 1300)
    sun_col = mul(fn, mask(fn, sun_col_raw, '', 200, 1300, r=True, g=True, b=True), '',
                  mask(fn, sun_col_raw, '', 200, 1360, a=True), '', 400, 1330)

    view = expr(fn, unreal.MaterialExpressionCameraVectorWS, 0, 1600)
    pixel_depth = expr(fn, unreal.MaterialExpressionPixelDepth, 0, 1700)

    # --- wetness -----------------------------------------------------------
    # The line and the amount are per primitive rather than per instance: every character in a level
    # is the same two material instances, and how wet each one is has to be able to differ without
    # any of them owning a material of their own.
    wet_line = cpd_scalar(fn, 'WetLine', 6, 0, 2400,
                          'Height of the waterline as a fraction of the object bounds. Written by '
                          'MobFortWetnessComponent as custom primitive data 6.')
    wet_amount = cpd_scalar(fn, 'Wetness', 7, 0, 2460,
                            'How wet the surface below the line is. Custom primitive data 7.')
    wet_soft = scalar_param(fn, 'WetSoftness', 0.04, GROUP_WET, 0, 2520, 0,
                            'How far the waterline fades out over, as a fraction of the bounds. '
                            'The drip line.')
    wet_darken = scalar_param(fn, 'WetDarken', 0.55, GROUP_WET, 0, 2580, 1,
                              'What the albedo is multiplied by where the surface is soaked.')
    wet_rough = scalar_param(fn, 'WetRoughness', 0.2, GROUP_WET, 0, 2640, 2,
                             'What the roughness is multiplied by where the surface is soaked. '
                             'This is the whole of the sheen: the panorama was already being read.')
    wet_flatten = scalar_param(fn, 'WetFlatten', 0.6, GROUP_WET, 0, 2700, 3,
                               'How far a film of water fills the normal detail in.')
    wet_pooling = scalar_param(fn, 'WetPooling', 0.5, GROUP_WET, 0, 2760, 4,
                               'How much the water prefers up-facing surfaces and creases over '
                               'covering everything evenly.')

    local_pos = expr(fn, unreal.MaterialExpressionLocalPosition, 0, 2820)
    bounds = expr(fn, unreal.MaterialExpressionObjectLocalBounds, 0, 2880)

    wet_mask = custom(fn, _CODE_WET_MASK, CMOT.CMOT_FLOAT1,
                      ['LocalPos', 'BoundsMin', 'BoundsMax', 'WetLine', 'Wetness', 'Softness'],
                      [], 400, 2600, 'Where the waterline sits on this object.')
    link(local_pos, 'XYZ', wet_mask, 'LocalPos')
    link(bounds, 'Min', wet_mask, 'BoundsMin')
    link(bounds, 'Max', wet_mask, 'BoundsMax')
    link(wet_line, '', wet_mask, 'WetLine')
    link(wet_amount, '', wet_mask, 'Wetness')
    link(wet_soft, '', wet_mask, 'Softness')

    # A constant zero rather than a switch around the whole response: the mask folds away and every
    # lerp it feeds folds with it, so a dry master pays for none of it and the shading code stays
    # one path.
    wet_gated = switch_param(fn, 'bWetness', wet_mask, '', const(fn, 0.0, 400, 2900), '',
                             GROUP_FEATURES, 600, 2700, default=False, sort=7,
                             desc='Wetness from the waterline a MobFortWetnessComponent writes. '
                                  'Off, the primitive data is never read and nothing downstream '
                                  'of it compiles.')

    surface = custom(
        fn, _CODE_SURFACE, CMOT.CMOT_FLOAT3,
        ['NormalTS', 'CRM', 'SunDirection', 'SpecDarken', 'Indirect', 'V', 'DepthParams', 'Depth',
         'AlbedoIn', 'WetMask', 'WetPooling', 'WetDarken', 'WetRoughness', 'WetFlatten',
         'LightDarken'],
        [('DiffuseTime', CMOT.CMOT_FLOAT1),
         ('NdotV', CMOT.CMOT_FLOAT1),
         ('R', CMOT.CMOT_FLOAT3),
         ('Albedo', CMOT.CMOT_FLOAT3),
         ('Cavity', CMOT.CMOT_FLOAT1),
         ('Roughness', CMOT.CMOT_FLOAT1),
         ('Metallic', CMOT.CMOT_FLOAT1),
         ('DiffuseScale', CMOT.CMOT_FLOAT1),
         ('SpecScale', CMOT.CMOT_FLOAT1),
         ('Brighten', CMOT.CMOT_FLOAT1),
         ('FresnelScale', CMOT.CMOT_FLOAT1),
         ('Wet', CMOT.CMOT_FLOAT1)],
        800, 1000, 'Shading vectors, texture pack and the clamped indirect and distance responses.')
    link(normal, 'RGB', surface, 'NormalTS')
    link(crm, '', surface, 'CRM')
    link(sun_dir, '', surface, 'SunDirection')
    link(spec_darken, '', surface, 'SpecDarken')
    link(indirect, '', surface, 'Indirect')
    link(view, '', surface, 'V')
    link(depth_params, '', surface, 'DepthParams')
    link(pixel_depth, 'R', surface, 'Depth')

    # Albedo goes through the node rather than round it because wetness darkens it, and the wet
    # normal has to reach the reflection vector as well.
    link(albedo, '', surface, 'AlbedoIn')
    link(wet_gated, '', surface, 'WetMask')
    link(wet_pooling, '', surface, 'WetPooling')
    link(wet_darken, '', surface, 'WetDarken')
    link(wet_rough, '', surface, 'WetRoughness')
    link(wet_flatten, '', surface, 'WetFlatten')

    # How far this character's surroundings are from the room the collection is lit for. Zero when
    # nothing writes it, which is a character lit exactly as the level says.
    area_darken = cpd_scalar(fn, 'LightDarken', 8, 0, 2960,
                             'How much darker this character is than the level, 0 to 1. Written by '
                             'MobWorld as custom primitive data 8.')
    area_gated = switch_param(fn, 'bAreaLighting', area_darken, '', const(fn, 0.0, 400, 3020), '',
                              GROUP_FEATURES, 600, 2980, default=False, sort=8,
                              desc='Let a volume darken this character without darkening every '
                                   'other one. Off, the primitive data is never read.')
    link(area_gated, '', surface, 'LightDarken')

    # --- specular ----------------------------------------------------------
    pano = texture_object_param(fn, 'SpecPanorama', TEX_PANORAMA, pano_type,
                                GROUP_TEXTURES, 0, 1900, 3)
    spec_scalar = scalar_param(fn, 'SpecularScalar', 0.12, GROUP_SPECULAR, 0, 2000, 0,
                               'Overall reflection strength. The panorama is HDR, so this is small.')
    max_mip = scalar_param(fn, 'MaxMip', 8.0, GROUP_SPECULAR, 0, 2100, 1,
                           'Mip a roughness of 1 reads. Roughly the mip at which the panorama is '
                           'a few pixels across.')
    fresnel_boost = scalar_param(fn, 'FresnelBoost', 2.0, GROUP_SPECULAR, 0, 2200, 2)

    fres_on = const(fn, 1.0, 0, 2300)
    fres_off = const(fn, 0.0, 0, 2400)
    fres_flag = switch_param(fn, 'bSpecularFresnel', fres_on, '', fres_off, '', GROUP_FEATURES,
                             200, 2350, default=True, sort=2,
                             desc='Grazing boost on the reflection. A captured cubemap has no '
                                  'hand-painted hot spots and reads flat without it.')

    spec = custom(
        fn, _CODE_SPECULAR, CMOT.CMOT_FLOAT3,
        ['Panorama', 'R', 'Albedo', 'Metallic', 'Roughness', 'NdotV', 'SpecularScalar', 'MaxMip',
         'FresnelBoost', 'bFresnel', 'SkyYaw'],
        [], 800, 2000,
        'One panorama tap at a roughness-chosen mip. There are no analytic highlights in this model.')
    link(pano, '', spec, 'Panorama')
    link(surface, 'R', spec, 'R')
    link(surface, 'Albedo', spec, 'Albedo')
    link(surface, 'Metallic', spec, 'Metallic')
    link(surface, 'Roughness', spec, 'Roughness')
    link(surface, 'NdotV', spec, 'NdotV')
    link(spec_scalar, '', spec, 'SpecularScalar')
    link(max_mip, '', spec, 'MaxMip')
    link(fresnel_boost, '', spec, 'FresnelBoost')
    link(fres_flag, '', spec, 'bFresnel')
    link(collection(fn, 'SkyYaw', 0, 2500), '', spec, 'SkyYaw')

    # --- outputs -----------------------------------------------------------
    outs = [
        ('Albedo', surface, 'Albedo'),
        ('DiffuseTime', surface, 'DiffuseTime'),
        ('SunColor', sun_col, ''),
        ('N', surface, ''),
        ('NdotV', surface, 'NdotV'),
        ('Specular', spec, ''),
        ('Cavity', surface, 'Cavity'),
        ('Emissive', emissive, ''),
        ('Roughness', surface, 'Roughness'),
        ('Metallic', surface, 'Metallic'),
        ('DiffuseScale', surface, 'DiffuseScale'),
        ('SpecScale', surface, 'SpecScale'),
        ('Brighten', surface, 'Brighten'),
        ('FresnelScale', surface, 'FresnelScale'),
        ('Wet', surface, 'Wet'),
    ]
    for i, (name, src, src_out) in enumerate(outs):
        out = fn_output(fn, name, 1200, i * 120, i)
        link(src, src_out, out, '')

    finish_function(fn)
    return fn


def build_gradient_diffuse_function():
    """MF_FortGradientDiffuse: the diffuse response, as a lookup rather than a curve.

    A half-Lambert term addresses a gradient, so an artist places the highlight, the mid tone and
    the core shadow, and the transitions between them, by moving stops. The ramp never reaches
    black at either end, which is what stands in for an ambient term.
    """
    fn = get_or_create_function(
        'MF_FortGradientDiffuse',
        'Gradient diffuse. Remapped N dot L reads a row of GA_FortCharacter, so the highlight, '
        'mid tone and core shadow and the transitions between them are all authored. Skin reads a '
        'redder row through the same term.')

    time_in = fn_input(fn, 'DiffuseTime', FIT.FUNCTION_INPUT_SCALAR, 0, 0, 0, 0.5,
                       'Remapped N dot L, from MF_FortSurface.')
    skin_in = fn_input(fn, 'SkinMask', FIT.FUNCTION_INPUT_SCALAR, 0, 120, 1, 0.0)
    b_skin = fn_input(fn, 'bSkin', FIT.FUNCTION_INPUT_STATIC_BOOL, 0, 240, 2, None,
                      'Blend a second, redder falloff in where the skin mask says so.')

    atlas = gradient_atlas_param(fn, 0, 360)
    row_body = gradient_row_param(fn, 'RowDiffuse', 'DiffuseFalloff', 0, 480, 1)
    row_skin = gradient_row_param(fn, 'RowSkinDiffuse', 'SkinDiffuseFalloff', 0, 600, 2)

    body = sample_gradient(fn, 'DiffuseFalloff', time_in, '', atlas, row_body, 400, 0)
    skin = sample_gradient(fn, 'SkinDiffuseFalloff', time_in, '', atlas, row_skin, 400, 200)
    blended = lerp(fn, body, 'RGB', skin, 'RGB', skin_in, '', 700, 100)
    result = switch(fn, b_skin, '', blended, '', body, 'RGB', 900, 50)

    link(result, '', fn_output(fn, 'Color', 1100, 0, 0), '')
    finish_function(fn)
    return fn


def build_weapon_diffuse_function():
    """MF_FortWeaponDiffuse: two colours and a soft edge, no gradient."""
    fn = get_or_create_function(
        'MF_FortWeaponDiffuse',
        'Smoothstep diffuse. A weapon is mostly shiny metal, so the specular carries it and the '
        'extra control a gradient gives has nothing to act on.')

    time_in = fn_input(fn, 'DiffuseTime', FIT.FUNCTION_INPUT_SCALAR, 0, 0, 0, 0.5)

    shadow_edge = scalar_param(fn, 'ShadowEdge', 0.35, GROUP_DIFFUSE, 0, 200, 0)
    light_edge = scalar_param(fn, 'LightEdge', 0.65, GROUP_DIFFUSE, 0, 300, 1)
    shadow_col = vector_param(fn, 'ShadowColor', (0.12, 0.13, 0.16, 1), GROUP_DIFFUSE, 0, 400, 2)
    light_col = vector_param(fn, 'LightColor', (1, 1, 1, 1), GROUP_DIFFUSE, 0, 500, 3)

    node = custom(fn, _CODE_WEAPON_DIFFUSE, CMOT.CMOT_FLOAT3,
                  ['DiffuseTime', 'ShadowEdge', 'LightEdge', 'ShadowColor', 'LightColor'],
                  [], 400, 200)
    link(time_in, '', node, 'DiffuseTime')
    link(shadow_edge, '', node, 'ShadowEdge')
    link(light_edge, '', node, 'LightEdge')
    link(shadow_col, '', node, 'ShadowColor')
    link(light_col, '', node, 'LightColor')

    link(node, '', fn_output(fn, 'Color', 700, 0, 0), '')
    finish_function(fn)
    return fn


def build_character_fx_function():
    """MF_FortCharacterFX: the team rim and the skin underglow.

    Both are additive terms that exist to make a character legible rather than to describe a
    surface, so they are kept out of the shared function and off the other two masters.
    """
    fn = get_or_create_function(
        'MF_FortCharacterFX',
        'Friend-or-foe rim and skin underglow. The rim is weighted toward up-facing surfaces and '
        'the upper body so it describes the silhouette instead of competing with it; the underglow '
        'is the wax look, strongest where the direct light is weakest.')

    n_in = fn_input(fn, 'N', FIT.FUNCTION_INPUT_VECTOR3, 0, 0, 0, (0, 0, 1))
    ndotv_in = fn_input(fn, 'NdotV', FIT.FUNCTION_INPUT_SCALAR, 0, 120, 1, 1.0)
    diffscale_in = fn_input(fn, 'DiffuseScale', FIT.FUNCTION_INPUT_SCALAR, 0, 240, 2, 1.0)
    fresscale_in = fn_input(fn, 'FresnelScale', FIT.FUNCTION_INPUT_SCALAR, 0, 360, 3, 1.0)
    b_rim = fn_input(fn, 'bFriendFoeRim', FIT.FUNCTION_INPUT_STATIC_BOOL, 0, 480, 4)
    b_glow = fn_input(fn, 'bUnderglow', FIT.FUNCTION_INPUT_STATIC_BOOL, 0, 600, 5)

    # Vertex colour rather than a fifth texture: a character is allowed four, and where skin is on
    # a body is exactly the kind of mask a channel can carry at vertex density.
    vcol = expr(fn, unreal.MaterialExpressionVertexColor, 0, 720)
    skin_amount = scalar_param(fn, 'SkinAmount', 0.0, GROUP_SKIN, 0, 840, 0,
                               'Scales the red vertex channel. An unpainted mesh reads white, so '
                               'this starts at zero and skin is opted into.')
    skin_mask = mul(fn, vcol, 'R', skin_amount, '', 300, 780)

    local_pos = expr(fn, unreal.MaterialExpressionLocalPosition, 0, 960)
    bounds = expr(fn, unreal.MaterialExpressionObjectLocalBounds, 0, 1080)

    up_bias = scalar_param(fn, 'RimUpBias', 0.35, GROUP_TEAM, 0, 1200, 2,
                           'How much the rim prefers up-facing surfaces.')
    height_bias = scalar_param(fn, 'RimHeightBias', 0.25, GROUP_TEAM, 0, 1300, 3,
                               'How much the rim prefers the upper body.')
    glow_power = scalar_param(fn, 'UnderglowPower', 2.5, GROUP_SKIN, 0, 1400, 1)
    glow_intensity = scalar_param(fn, 'UnderglowIntensity', 1.0, GROUP_SKIN, 0, 1500, 2)
    rim_intensity = scalar_param(fn, 'RimIntensity', 1.5, GROUP_TEAM, 0, 1600, 1)

    masks = custom(
        fn, _CODE_CHARACTER_MASKS, CMOT.CMOT_FLOAT1,
        ['N', 'NdotV', 'LocalPos', 'BoundsMin', 'BoundsMax', 'UpBias', 'HeightBias',
         'FresnelScale', 'UnderglowPower', 'DiffuseScale'],
        [('Underglow', CMOT.CMOT_FLOAT1)],
        600, 1100, 'Returns the rim mask; Underglow is the wax term.')
    link(n_in, '', masks, 'N')
    link(ndotv_in, '', masks, 'NdotV')
    link(local_pos, 'XYZ', masks, 'LocalPos')
    link(bounds, 'Min', masks, 'BoundsMin')
    link(bounds, 'Max', masks, 'BoundsMax')
    link(up_bias, '', masks, 'UpBias')
    link(height_bias, '', masks, 'HeightBias')
    link(fresscale_in, '', masks, 'FresnelScale')
    link(glow_power, '', masks, 'UnderglowPower')
    link(diffscale_in, '', masks, 'DiffuseScale')

    atlas = gradient_atlas_param(fn, 0, 1700)
    row_enemy = gradient_row_param(fn, 'RowRimEnemy', 'FresnelEnemy', 0, 1800, 3)
    row_ally = gradient_row_param(fn, 'RowRimAlly', 'FresnelAlly', 0, 1900, 4)
    row_glow = gradient_row_param(fn, 'RowUnderglow', 'SkinUnderglow', 0, 2000, 5)

    # Two rows and a static switch rather than one row and a lerp: ally and enemy are different
    # material instances, so only one of these ever compiles.
    enemy = sample_gradient(fn, 'FresnelEnemy', masks, '', atlas, row_enemy, 900, 1000)
    ally = sample_gradient(fn, 'FresnelAlly', masks, '', atlas, row_ally, 900, 1200)
    rim_col = switch_param(fn, 'bEnemy', enemy, 'RGB', ally, 'RGB', GROUP_TEAM, 1100, 1100,
                           default=False, sort=0,
                           desc='Which side of the rim gradient this instance reads.')
    rim = mul(fn, rim_col, '', rim_intensity, '', 1300, 1100)
    rim_gated = switch(fn, b_rim, '', rim, '', const3(fn, (0, 0, 0), 1300, 1300), '', 1500, 1150)

    glow_col = sample_gradient(fn, 'SkinUnderglow', masks, 'Underglow', atlas, row_glow, 900, 1500)
    glow = mul(fn, mul(fn, glow_col, 'RGB', glow_intensity, '', 1100, 1500), '',
               skin_mask, '', 1300, 1500)
    glow_gated = switch(fn, b_glow, '', glow, '', const3(fn, (0, 0, 0), 1300, 1700), '', 1500, 1550)

    extra = add(fn, rim_gated, '', glow_gated, '', 1700, 1300)

    for i, (name, src, src_out) in enumerate([
            ('Extra', extra, ''),
            ('SkinMask', skin_mask, ''),
            ('RimMask', masks, ''),
            ('UnderglowMask', masks, 'Underglow')]):
        link(src, src_out, fn_output(fn, name, 1900, i * 120, i), '')

    finish_function(fn)
    return fn


# Mode order has to match FortDebugView in the ush.
_DEBUG_MODES = ('0 off, 1 diffuse, 2 specular, 3 world normal, 4 cavity, 5 rim mask, 6 skin mask, '
                '7 underglow, 8 distance brighten, 9 roughness, 10 metallic, 11 wetness')


def build_compose_function():
    """MF_FortCompose: the sum, and the debug view that replaces it.

    Everything lands on emissive because the masters are unlit and no other pin survives to the
    frame. The two quality switches are here rather than in the master so that turning one off
    discards the input, and the whole chain behind it stops compiling.
    """
    fn = get_or_create_function(
        'MF_FortCompose',
        'Sums the shaded terms to one emissive colour, and carries the debug view. bUseDiffuse and '
        'bUseSpecular discard a whole response, which is how this scales down.')

    y = 0

    def _in(name, itype, default=None, desc=''):
        nonlocal y
        e = fn_input(fn, name, itype, 0, y, y // 120, default, desc)
        y += 120
        return e

    albedo = _in('Albedo', FIT.FUNCTION_INPUT_VECTOR3, (1, 1, 1))
    diffuse = _in('Diffuse', FIT.FUNCTION_INPUT_VECTOR3, (1, 1, 1))
    sun_color = _in('SunColor', FIT.FUNCTION_INPUT_VECTOR3, (1, 1, 1))
    cavity = _in('Cavity', FIT.FUNCTION_INPUT_SCALAR, 1.0)
    diffuse_scale = _in('DiffuseScale', FIT.FUNCTION_INPUT_SCALAR, 1.0)
    specular = _in('Specular', FIT.FUNCTION_INPUT_VECTOR3, (0, 0, 0))
    spec_scale = _in('SpecScale', FIT.FUNCTION_INPUT_SCALAR, 1.0)
    emissive = _in('Emissive', FIT.FUNCTION_INPUT_SCALAR, 0.0)
    extra = _in('Extra', FIT.FUNCTION_INPUT_VECTOR3, (0, 0, 0))
    brighten = _in('Brighten', FIT.FUNCTION_INPUT_SCALAR, 0.0)
    b_diffuse = _in('bUseDiffuse', FIT.FUNCTION_INPUT_STATIC_BOOL, None,
                    'Off drops the whole diffuse response and its gradient tap.')
    b_specular = _in('bUseSpecular', FIT.FUNCTION_INPUT_STATIC_BOOL, None,
                     'Off drops the cubemap tap.')
    # Left unconnected on the masters that have no such term, where they read these defaults.
    normal = _in('N', FIT.FUNCTION_INPUT_VECTOR3, (0, 0, 1), 'Debug only.')
    rim_mask = _in('RimMask', FIT.FUNCTION_INPUT_SCALAR, 0.0, 'Debug only.')
    skin_mask = _in('SkinMask', FIT.FUNCTION_INPUT_SCALAR, 0.0, 'Debug only.')
    underglow = _in('UnderglowMask', FIT.FUNCTION_INPUT_SCALAR, 0.0, 'Debug only.')
    roughness = _in('Roughness', FIT.FUNCTION_INPUT_SCALAR, 0.5, 'Debug only.')
    metallic = _in('Metallic', FIT.FUNCTION_INPUT_SCALAR, 0.0, 'Debug only.')
    wet = _in('Wet', FIT.FUNCTION_INPUT_SCALAR, 0.0, 'Debug only.')

    diffuse_used = switch(fn, b_diffuse, '', diffuse, '', const3(fn, (1, 1, 1), 300, 100), '',
                          500, 50)
    spec_used = switch(fn, b_specular, '', specular, '', const3(fn, (0, 0, 0), 300, 300), '',
                       500, 250)

    node = custom(fn, _CODE_COMPOSE, CMOT.CMOT_FLOAT3,
                  ['Albedo', 'Diffuse', 'SunColor', 'Cavity', 'DiffuseScale', 'Specular',
                   'SpecScale', 'Emissive', 'Extra', 'Brighten'],
                  [], 800, 200)
    link(albedo, '', node, 'Albedo')
    link(diffuse_used, '', node, 'Diffuse')
    link(sun_color, '', node, 'SunColor')
    link(cavity, '', node, 'Cavity')
    link(diffuse_scale, '', node, 'DiffuseScale')
    link(spec_used, '', node, 'Specular')
    link(spec_scale, '', node, 'SpecScale')
    link(emissive, '', node, 'Emissive')
    link(extra, '', node, 'Extra')
    link(brighten, '', node, 'Brighten')

    mode = scalar_param(fn, 'DebugMode', 1.0, GROUP_DEBUG, 300, 900, 1, _DEBUG_MODES)
    debug = custom(fn, _CODE_DEBUG, CMOT.CMOT_FLOAT3,
                   ['Mode', 'Diffuse', 'Specular', 'N', 'Cavity', 'Fresnel', 'SkinMask',
                    'Underglow', 'Brighten', 'Roughness', 'Metallic', 'Wet'],
                   [], 800, 900, 'Never compiled unless bDebug is on.')
    link(mode, '', debug, 'Mode')
    link(diffuse_used, '', debug, 'Diffuse')
    link(spec_used, '', debug, 'Specular')
    link(normal, '', debug, 'N')
    link(cavity, '', debug, 'Cavity')
    link(rim_mask, '', debug, 'Fresnel')
    link(skin_mask, '', debug, 'SkinMask')
    link(underglow, '', debug, 'Underglow')
    link(brighten, '', debug, 'Brighten')
    link(roughness, '', debug, 'Roughness')
    link(metallic, '', debug, 'Metallic')
    link(wet, '', debug, 'Wet')

    result = switch_param(fn, 'bDebug', debug, '', node, '', GROUP_DEBUG, 1100, 500,
                          default=False, sort=0,
                          desc='Replaces the shaded result with one intermediate. ' + _DEBUG_MODES)

    link(result, '', fn_output(fn, 'Color', 1400, 0, 0), '')
    finish_function(fn)
    return fn


def build_functions():
    build_surface_function()
    build_gradient_diffuse_function()
    build_weapon_diffuse_function()
    build_character_fx_function()
    build_compose_function()
    _log('functions built')


# ---------------------------------------------------------------------------
# Phase 5 - masters
# ---------------------------------------------------------------------------

def _finish_master(mat, color_expr, color_out=''):
    mat.set_editor_property('shading_model', unreal.MaterialShadingModel.MSM_UNLIT)
    mat.set_editor_property('blend_mode', unreal.BlendMode.BLEND_OPAQUE)
    mat.set_editor_property('two_sided', False)
    MEL.connect_material_property(color_expr, color_out, MP.MP_EMISSIVE_COLOR)
    _spread(MEL.get_material_expressions(mat))
    errors = MEL.recompile_material(mat)
    save(mat)
    return errors


def _quality_switches(mat, compose, x, y):
    """The two feature bools every master carries."""
    link(bool_param(mat, 'bUseDiffuse', True, GROUP_FEATURES, x, y, 10,
                    'Off drops the diffuse response entirely.'), '', compose, 'bUseDiffuse')
    link(bool_param(mat, 'bUseSpecular', True, GROUP_FEATURES, x, y + 120, 11,
                    'Off drops the cubemap tap.'), '', compose, 'bUseSpecular')


def _wire_common(mat, surface, compose):
    link(surface, 'Albedo', compose, 'Albedo')
    link(surface, 'SunColor', compose, 'SunColor')
    link(surface, 'Cavity', compose, 'Cavity')
    link(surface, 'DiffuseScale', compose, 'DiffuseScale')
    link(surface, 'Specular', compose, 'Specular')
    link(surface, 'SpecScale', compose, 'SpecScale')
    link(surface, 'Emissive', compose, 'Emissive')
    link(surface, 'Brighten', compose, 'Brighten')
    link(surface, 'N', compose, 'N')
    link(surface, 'Roughness', compose, 'Roughness')
    link(surface, 'Metallic', compose, 'Metallic')
    link(surface, 'Wet', compose, 'Wet')


def build_base_master():
    """M_FortBase: props and environment.

    The three universal responses and nothing else. Also the reference the other two are read
    against: anything in here that is not in them is a difference worth justifying.
    """
    mat = get_or_create_material('M_FortBase')
    mat.set_editor_property('used_with_instanced_static_meshes', True)

    surface = fn_call(mat, 'MF_FortSurface', 0, 0)
    diffuse = fn_call(mat, 'MF_FortGradientDiffuse', 400, 0)
    link(surface, 'DiffuseTime', diffuse, 'DiffuseTime')
    link(const(mat, 0.0, 200, 200), '', diffuse, 'SkinMask')
    link(expr(mat, unreal.MaterialExpressionStaticBool, 200, 300), '', diffuse, 'bSkin')

    compose = fn_call(mat, 'MF_FortCompose', 800, 0)
    _wire_common(mat, surface, compose)
    link(diffuse, '', compose, 'Diffuse')
    _quality_switches(mat, compose, 400, 600)

    return mat, _finish_master(mat, compose)


def build_character_master():
    """M_FortCharacter: the one that has to stay legible.

    Everything the base master has, plus the two terms that exist for the player rather than for
    the surface: the team rim and the skin underglow.
    """
    mat = get_or_create_material('M_FortCharacter')
    mat.set_editor_property('used_with_skeletal_mesh', True)

    surface = fn_call(mat, 'MF_FortSurface', 0, 0)

    fx = fn_call(mat, 'MF_FortCharacterFX', 400, 400)
    link(surface, 'N', fx, 'N')
    link(surface, 'NdotV', fx, 'NdotV')
    link(surface, 'DiffuseScale', fx, 'DiffuseScale')
    link(surface, 'FresnelScale', fx, 'FresnelScale')
    link(bool_param(mat, 'bFriendFoeRim', True, GROUP_FEATURES, 200, 400, 5), '',
         fx, 'bFriendFoeRim')
    link(bool_param(mat, 'bUnderglow', True, GROUP_FEATURES, 200, 520, 6,
                    'Skin underglow. Costs nothing on a mesh whose SkinAmount is zero, but it '
                    'still compiles, so a character with no skin should turn it off.'), '',
         fx, 'bUnderglow')

    diffuse = fn_call(mat, 'MF_FortGradientDiffuse', 800, 0)
    link(surface, 'DiffuseTime', diffuse, 'DiffuseTime')
    link(fx, 'SkinMask', diffuse, 'SkinMask')
    link(bool_param(mat, 'bSkin', True, GROUP_FEATURES, 600, 200, 4,
                    'Blends the redder skin falloff in where the red vertex channel says so.'), '',
         diffuse, 'bSkin')

    compose = fn_call(mat, 'MF_FortCompose', 1200, 0)
    _wire_common(mat, surface, compose)
    link(diffuse, '', compose, 'Diffuse')
    link(fx, 'Extra', compose, 'Extra')
    link(fx, 'RimMask', compose, 'RimMask')
    link(fx, 'SkinMask', compose, 'SkinMask')
    link(fx, 'UnderglowMask', compose, 'UnderglowMask')
    _quality_switches(mat, compose, 800, 800)

    return mat, _finish_master(mat, compose)


def build_weapon_master():
    """M_FortWeapon: the older styling, on the thing that never needed the newer one."""
    mat = get_or_create_material('M_FortWeapon')
    mat.set_editor_property('used_with_skeletal_mesh', True)

    surface = fn_call(mat, 'MF_FortSurface', 0, 0)
    diffuse = fn_call(mat, 'MF_FortWeaponDiffuse', 400, 0)
    link(surface, 'DiffuseTime', diffuse, 'DiffuseTime')

    compose = fn_call(mat, 'MF_FortCompose', 800, 0)
    _wire_common(mat, surface, compose)
    link(diffuse, '', compose, 'Diffuse')
    _quality_switches(mat, compose, 400, 600)

    return mat, _finish_master(mat, compose)


def build_masters():
    results = []
    for builder in (build_base_master, build_character_master, build_weapon_master):
        mat, errors = builder()
        results.append((mat, errors))
        if errors:
            for e in errors:
                unreal.log_error('[MobFort] %s: %s' % (mat.get_name(), e))
        else:
            _log('%s compiled clean' % mat.get_name())
    return results


# ---------------------------------------------------------------------------
# Phase 6 - instances
# ---------------------------------------------------------------------------

# A grey albedo rather than white: the placeholder is a flat colour with no texture detail, and a
# white one clips the moment the reflection lands on it, taking the gradient with it.
DEMO_TINT = (0.18, 0.18, 0.20, 1.0)

INSTANCES = [
    ('MI_FortCharacter_Ally', 'M_FortCharacter', {}, {'bEnemy': False}, DEMO_TINT),
    ('MI_FortCharacter_Enemy', 'M_FortCharacter', {}, {'bEnemy': True}, DEMO_TINT),
    ('MI_FortWeapon_Demo', 'M_FortWeapon', {'Roughness': 0.25}, {}, DEMO_TINT),
    ('MI_FortBase_Demo', 'M_FortBase', {'Roughness': 0.6}, {}, DEMO_TINT),
]


def build_instances():
    made = []
    for name, parent, scalars, switches, tint in INSTANCES:
        path = INST_ROOT + '/' + name
        if EAL.does_asset_exist(path):
            mi = unreal.load_asset(path)
        else:
            mi = _tools().create_asset(name, INST_ROOT, unreal.MaterialInstanceConstant,
                                       unreal.MaterialInstanceConstantFactoryNew())
        MEL.set_material_instance_parent(mi, unreal.load_asset(ROOT + '/' + parent))
        for k, v in scalars.items():
            MEL.set_material_instance_scalar_parameter_value(mi, k, float(v))
        for k, v in switches.items():
            MEL.set_material_instance_static_switch_parameter_value(mi, k, bool(v))
        if tint:
            MEL.set_material_instance_vector_parameter_value(mi, 'Tint', LC(*tint))
        MEL.update_material_instance(mi)
        save(mi)
        made.append(name)
    _log('instances: %s' % ', '.join(made))
    return made


# ---------------------------------------------------------------------------
# Everything
# ---------------------------------------------------------------------------

def build_all():
    # Reloaded here rather than left to the caller: save() holds the reference, so a stamp edited
    # during a session would otherwise keep writing the version it was imported with.
    importlib.reload(fort_version)
    _log('authoring %s' % fort_version.plugin_version())

    build_textures()
    build_gradients()
    build_lighting_collection()
    build_functions()
    results = build_masters()
    build_instances()

    _log('--- statistics ---')
    for mat, errors in results:
        s = MEL.get_statistics(mat)
        _log('%-18s errors %-2d  pixel %-5s  tex %-3s  samplers %s'
             % (mat.get_name(), len(errors),
                s.get_editor_property('num_pixel_shader_instructions'),
                s.get_editor_property('num_pixel_texture_samples'),
                s.get_editor_property('num_samplers')))

    EAL.save_directory(ROOT, only_if_is_dirty=False, recursive=True)
    return all(not errors for _, errors in results)
