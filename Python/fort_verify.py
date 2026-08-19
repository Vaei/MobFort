"""Checks the MobFort masters against the claims the design makes.

Not a diff against a golden copy: a binary diff of a material says something changed without saying
whether it matters. These are the claims - what a feature costs, what turning it off gives back -
asserted one at a time, so a failure names the claim that stopped being true.

    import sys, importlib
    sys.path.append('<PluginDir>/Python')
    import fort_verify
    importlib.reload(fort_verify)
    fort_verify.run()

Permutations are measured on transient material instances rather than scratch assets. An asset
created and deleted inside one call raises a modal "asset is in use" dialog that blocks the game
thread with nothing on the other end to dismiss it.

Every number is the Material Editor's own estimate rather than a count of taps in the compiled
shader. The estimate over-reports, so these are baselines to hold steady, not ground truth.
"""

import importlib

import unreal

import fort_version

MEL = unreal.MaterialEditingLibrary
EAL = unreal.EditorAssetLibrary

ROOT = '/MobFort'

SWITCHES = ['bUseDiffuse', 'bUseSpecular', 'bSpecularFresnel', 'bUseCRMTexture', 'bEmissive',
            'bFriendFoeRim', 'bSkin', 'bUnderglow', 'bEnemy', 'bWetness', 'bDebug']

FULL = {'bUseDiffuse', 'bUseSpecular', 'bSpecularFresnel'}
CHARACTER_FULL = FULL | {'bFriendFoeRim', 'bSkin', 'bUnderglow'}


# Also kept in memory so a caller driving this headlessly gets the report back rather than having
# to go and read the editor log.
REPORT = []


def _log(msg):
    REPORT.append(str(msg))
    unreal.log('[FortVerify] ' + str(msg))


# Instances are kept between runs so their shaders survive to the next one. A permutation nobody
# has ever compiled has no shader map to report, and one call cannot both request the compile and
# wait for it: the game thread is what finishes a compile, and this is running on it. So on a cold
# derived data cache the first run reports some permutations as uncompiled and the second, once the
# editor has ticked, measures them.
_INSTANCES = {}


def _instance(mat, on):
    """A transient instance with exactly the named switches on."""
    key = (mat.get_path_name(), tuple(sorted(on)))
    if key in _INSTANCES:
        return _INSTANCES[key]
    mi = unreal.new_object(unreal.MaterialInstanceConstant)
    MEL.set_material_instance_parent(mi, mat)
    for sw in SWITCHES:
        MEL.set_material_instance_static_switch_parameter_value(mi, sw, sw in on)
    MEL.update_material_instance(mi)
    _INSTANCES[key] = mi
    return mi


def _read(mi):
    s = MEL.get_statistics(mi)
    return {
        'ps': s.get_editor_property('num_pixel_shader_instructions'),
        'vs': s.get_editor_property('num_vertex_shader_instructions'),
        'tex': s.get_editor_property('num_pixel_texture_samples'),
        'samplers': s.get_editor_property('num_samplers'),
    }


def measure(mat, cases):
    """Statistics for several static permutations at once, keyed by label.

    Every instance is built before any is read. A permutation nobody has compiled before reports
    zero instructions rather than an error, and building them all first gives the compile that
    much longer to land - reading each one as it is made reliably loses the last of them.
    """
    made = [(label, _instance(mat, on)) for label, on in cases]
    out = {}
    for label, mi in made:
        s = _read(mi)
        # Re-read once; the shader map may have arrived while the earlier ones were being read.
        if not s['ps']:
            s = _read(mi)
        out[label] = s
    return out


class _Result(object):
    def __init__(self):
        self.passed = 0
        self.failed = []

    def check(self, claim, ok, detail=''):
        if ok:
            self.passed += 1
            _log('  pass  %s%s' % (claim, (' - ' + detail) if detail else ''))
        else:
            self.failed.append(claim)
            _log('  FAIL  %s%s' % (claim, (' - ' + detail) if detail else ''))


def run():
    del REPORT[:]
    r = _Result()
    masters = {}

    for name in ('M_FortBase', 'M_FortCharacter', 'M_FortWeapon'):
        mat = unreal.load_asset(ROOT + '/' + name)
        if mat is None:
            r.check('%s exists' % name, False)
            continue
        masters[name] = mat

        # A master goes stale when a function it calls is rebuilt without it, and the errors land
        # nowhere near the function, so compiling is asserted before anything is measured.
        r.check('%s compiles' % name, len(MEL.recompile_material(mat)) == 0)

        # Unlit is the whole premise. A master that came back as lit would render, and would be
        # lit by a renderer this model assumes contributes nothing.
        r.check('%s is unlit' % name,
                'UNLIT' in str(mat.get_editor_property('shading_model')).upper())

        # Every term lands on emissive. Anything reaching base colour is being lit twice or not
        # at all, depending on the renderer.
        base = MEL.get_material_property_input_node(mat, unreal.MaterialProperty.MP_BASE_COLOR) \
            if hasattr(MEL, 'get_material_property_input_node') else None
        r.check('%s writes nothing to base colour' % name, base is None)

        # The point of moving the maths to a ush. A master that has grown a graph again is a
        # master someone edited by hand instead of editing the builder.
        count = len(MEL.get_material_expressions(mat))
        r.check('%s master graph stays small' % name, count <= 16, '%d nodes' % count)

    _log('--- permutations ---')

    # num_pixel_texture_samples counts TextureSample expressions in the graph and cannot see a tap
    # a Custom node takes for itself, so the panorama is invisible to it. Its sampler still shows
    # up in num_samplers, which is what the specular claims are asserted against.
    GRADIENT_MASTERS = ('M_FortBase', 'M_FortCharacter')

    measured = {}
    for name, mat in masters.items():
        full = CHARACTER_FULL if name == 'M_FortCharacter' else FULL
        cases = [
            ('off', set()),
            ('full', full),
            ('no diffuse', full - {'bUseDiffuse'}),
            ('no specular', full - {'bUseSpecular'}),
            ('debug off', FULL),
            ('debug on', FULL | {'bDebug'}),
            ('crm texture', full | {'bUseCRMTexture'}),
            ('emissive', full | {'bEmissive'}),
            ('wet', full | {'bWetness'}),
        ]
        if name == 'M_FortCharacter':
            cases += [('no %s' % s, full - {s})
                      for s in ('bFriendFoeRim', 'bSkin', 'bUnderglow')]
            cases += [('enemy', full | {'bEnemy'})]
        measured[name] = measure(mat, cases)

    for name, mat in masters.items():
        m = measured[name]

        # A permutation with no shader map reads as zero instructions, and so does one that failed
        # to compile - the two are indistinguishable from here. Treated as a failure rather than
        # skipped, because a branch that is off by default is exactly where a compile error hides:
        # nothing else in this project ever asks for it.
        uncompiled = sorted(k for k, v in m.items() if not v['ps'])
        r.check('%s every permutation has a shader map' % name, not uncompiled,
                ('uncompiled: ' + ', '.join(uncompiled) + ' (on a cold derived data cache, run '
                 'this a second time before believing it)') if uncompiled else '')

        on, off = m['full'], m['off']
        _log('%s  off %s  full %s' % (name, off, on))

        # A shared sampler for the surface taps, one for the gradient atlas and one for the
        # panorama. Nowhere near the 16 the platform allows, and it must stay that way.
        r.check('%s sampler budget never approached' % name, on['samplers'] <= 8,
                'full uses %s' % on['samplers'])

        # The claim the whole gating design rests on: a discarded function input takes its texture
        # taps with it, not just its arithmetic.
        no_spec = m['no specular']
        if no_spec['ps']:
            r.check('%s dropping specular gives back the panorama tap' % name,
                    no_spec['samplers'] < on['samplers'] and no_spec['ps'] < on['ps'],
                    'samplers %s -> %s, ps %s -> %s'
                    % (on['samplers'], no_spec['samplers'], on['ps'], no_spec['ps']))

        no_diffuse = m['no diffuse']
        if no_diffuse['ps']:
            gave_back_tap = no_diffuse['tex'] < on['tex'] if name in GRADIENT_MASTERS else True
            r.check('%s dropping diffuse gives back its cost' % name,
                    gave_back_tap and no_diffuse['ps'] < on['ps'],
                    'tex %s -> %s, ps %s -> %s'
                    % (on['tex'], no_diffuse['tex'], on['ps'], no_diffuse['ps']))

        # Debug is a whole second shading path, and the claim that matters is that it is absent
        # when off. That cannot be measured directly - there is no build without it to compare
        # against - so this is the floor: turning it off never costs more than leaving it on.
        # Whether the switch is live at all is asserted on the character below, where the debug
        # node reads masks nothing else does and the two paths cannot fold together.
        if m['debug on']['ps'] and m['debug off']['ps']:
            r.check('%s debug never costs more when off' % name,
                    m['debug off']['ps'] <= m['debug on']['ps'],
                    'ps %s off, %s on' % (m['debug off']['ps'], m['debug on']['ps']))

        # The scalar path exists so a prop with no pack still works. It must be the cheaper one,
        # or nobody has a reason to use it.
        with_tex = m['crm texture']
        if with_tex['ps']:
            r.check('%s the CRM texture costs a tap over the scalars' % name,
                    with_tex['tex'] > on['tex'], 'tex %s -> %s' % (on['tex'], with_tex['tex']))

        # Emissive rides the albedo's alpha, so it may cost arithmetic but never another tap.
        emissive = m['emissive']
        if emissive['ps']:
            r.check('%s emissive costs no texture of its own' % name,
                    emissive['tex'] == on['tex'] and emissive['samplers'] == on['samplers'],
                    'tex %s -> %s' % (on['tex'], emissive['tex']))

        # Wetness reads primitive data and rewrites terms that are already there. If it ever costs
        # a tap, something has grown a mask texture that the design says it does not have.
        wet = m['wet']
        if wet['ps']:
            r.check('%s wetness costs no texture of its own' % name,
                    wet['tex'] == on['tex'] and wet['samplers'] == on['samplers'],
                    'tex %s -> %s, samplers %s -> %s'
                    % (on['tex'], wet['tex'], on['samplers'], wet['samplers']))

            # The switch has to be live. Off, the mask is a constant zero, every lerp it feeds folds
            # and the primitive data is never read - so this permutation must be the dearer one.
            r.check('%s wetness gives its cost back when off' % name,
                    on['ps'] < wet['ps'], 'ps %s off, %s on' % (on['ps'], wet['ps']))

    if 'M_FortCharacter' in masters:
        m = measured['M_FortCharacter']
        full = m['full']

        # Each of the three character terms has to be worth switching off individually, or the
        # switch is a lie and the master should just always pay for it.
        for switch_name in ('bFriendFoeRim', 'bSkin', 'bUnderglow'):
            without = m['no ' + switch_name]
            if without['ps']:
                r.check('character %s costs something' % switch_name,
                        without['ps'] < full['ps'],
                        'ps %s -> %s' % (without['ps'], full['ps']))

        # The one place the debug switch can be caught being dead: the character feeds it the rim,
        # skin and underglow masks, which nothing on the shaded path reads, so the two branches
        # cannot compile to the same thing the way they do on a master that leaves them constant.
        if m['debug on']['ps'] and m['debug off']['ps']:
            r.check('the debug switch is live',
                    m['debug off']['ps'] < m['debug on']['ps'],
                    'ps %s off, %s on' % (m['debug off']['ps'], m['debug on']['ps']))

        # Ally and enemy are separate instances, so only one rim gradient may ever compile.
        if m['enemy']['ps']:
            r.check('the rim gradient is one tap, not two',
                    m['enemy']['tex'] == full['tex'],
                    'tex %s and %s' % (full['tex'], m['enemy']['tex']))

        # A character costs more than a prop, and that is the right way round. If it ever inverts,
        # something in the base master has grown that does not belong there.
        base_full = measured['M_FortBase']['full']
        r.check('the character master is the expensive one',
                full['ps'] > base_full['ps'],
                'character %s, base %s' % (full['ps'], base_full['ps']))

    ga = unreal.load_asset(ROOT + '/Gradients/GA_FortCharacter')
    if ga is not None:
        rows = [str(n) for n in ga.get_gradient_names()]
        r.check('the plugin atlas still has the rows the row defaults name',
                rows == ['DiffuseFalloff', 'SkinDiffuseFalloff', 'SkinUnderglow',
                         'FresnelEnemy', 'FresnelAlly'], str(rows))
        tex = ga.get_editor_property('texture')
        r.check('the atlas is baked', tex is not None and tex.blueprint_get_size_y() == len(rows),
                '%dx%d' % (tex.blueprint_get_size_x(), tex.blueprint_get_size_y()) if tex else 'none')

    # A project swaps atlases per character, so the atlas has to be a parameter rather than the
    # asset the functions were authored against, and the row has to be a parameter rather than an
    # index resolved from a gradient name at compile time. Without both, changing atlas means
    # editing this plugin's content.
    for name, expect_rows in (('M_FortBase', ['RowDiffuse', 'RowSkinDiffuse']),
                              ('M_FortCharacter', ['RowDiffuse', 'RowSkinDiffuse', 'RowUnderglow',
                                                   'RowRimEnemy', 'RowRimAlly'])):
        mat = masters.get(name)
        if mat is None:
            continue
        textures = [str(x) for x in MEL.get_texture_parameter_names(mat)]
        scalars = [str(x) for x in MEL.get_scalar_parameter_names(mat)]
        r.check('%s exposes the gradient atlas' % name, 'Atlas' in textures, str(textures))
        missing = [x for x in expect_rows if x not in scalars]
        r.check('%s exposes every row it reads' % name, not missing,
                ('missing ' + ', '.join(missing)) if missing else ', '.join(expect_rows))

    # Every gradient tap goes through one atlas parameter, so a character reading four rows spends
    # one sampler on them, not four.
    if 'M_FortCharacter' in masters:
        ch_full = measured['M_FortCharacter']['full']
        r.check('four gradient rows share one sampler', ch_full['samplers'] <= 3,
                'full uses %s samplers for %s taps' % (ch_full['samplers'], ch_full['tex']))

    pano = unreal.load_asset(ROOT + '/Textures/T_BaseHDRI')
    if pano is not None:
        # Roughness picks a mip. Without a chain every roughness is a mirror, and the material
        # still compiles and still renders, so nothing else catches this.
        r.check('the panorama has a mip chain',
                str(pano.get_editor_property('mip_gen_settings')).find('NO_MIPMAPS') < 0,
                str(pano.get_editor_property('mip_gen_settings')))

    # Everything above compares the content against itself, so it passes just as happily on content
    # an older plugin built. This is the only check that can tell that apart.
    importlib.reload(fort_version)
    _log('--- version %s ---' % fort_version.plugin_version())
    for failure in fort_version.check():
        r.check(failure, False)

    _log('%d passed, %d failed' % (r.passed, len(r.failed)))
    for f in r.failed:
        _log('  failed: %s' % f)
    return not r.failed
