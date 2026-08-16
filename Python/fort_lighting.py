"""Writes a level's directional light into MPC_FortLighting.

    import sys, importlib
    sys.path.append('<PluginDir>/Python')
    import fort_lighting
    fort_lighting.sync_sun()

Nothing in MobFort reads a light actor. The masters are Unlit, so the engine never hands them one,
and the collection is the only thing they shade against - which means rotating the level's sun
changes nothing on a character until this runs.

One shot, and it saves the collection. A sun that moves during play wants the level Blueprint
writing the same two parameters every tick instead.
"""

import unreal

MEL = unreal.MaterialEditingLibrary
EAL = unreal.EditorAssetLibrary

LIGHTING_MPC = '/MobFort/MPC_FortLighting'


def _log(msg):
    unreal.log('[MobFort] ' + str(msg))


def find_sun():
    """The first directional light in the open level, or None."""
    els = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    for actor in els.get_all_level_actors():
        if isinstance(actor, unreal.DirectionalLight):
            return actor
    return None


def _vector_default(mpc, name):
    for p in mpc.get_editor_property('vector_parameters'):
        if str(p.get_editor_property('parameter_name')) == name:
            return p.get_editor_property('default_value')
    return None


def _set_vector_default(mpc, name, value):
    """Writes one vector parameter's default.

    Assigned back by index. Iterating the array hands out copies of each struct, so mutating the
    loop variable writes to something nobody reads and the call looks like it worked.
    """
    params = mpc.get_editor_property('vector_parameters')
    found = False
    for i in range(len(params)):
        entry = params[i]
        if str(entry.get_editor_property('parameter_name')) != name:
            continue
        entry.set_editor_property('default_value', value)
        params[i] = entry
        found = True

    if not found:
        unreal.log_warning('[MobFort] %s has no vector parameter named %s'
                           % (mpc.get_name(), name))
        return False

    mpc.set_editor_property('vector_parameters', params,
                            unreal.PropertyAccessChangeNotifyMode.ALWAYS)
    return True


def sync_sun(light_path=None):
    """Points SunDirection at the light and takes SunColor from it.

    Returns True when it wrote something.
    """
    light = unreal.load_object(None, light_path) if light_path else find_sun()
    if light is None:
        unreal.log_warning('[MobFort] no directional light in this level')
        return False

    mpc = unreal.load_asset(LIGHTING_MPC)
    if mpc is None:
        unreal.log_warning('[MobFort] %s is missing' % LIGHTING_MPC)
        return False

    component = light.get_component_by_class(unreal.DirectionalLightComponent)
    if component is None:
        unreal.log_warning('[MobFort] %s has no light component' % light.get_actor_label())
        return False

    # A light points along its forward vector, and the shading wants the direction toward the
    # light, so the sun direction is the negated forward vector.
    forward = light.get_actor_forward_vector()
    direction = unreal.Vector(-forward.x, -forward.y, -forward.z).normal()

    # W carries nothing, so it is written as zero rather than preserved. Anything parked there
    # would be clobbered by an external tool writing the light vector as a whole colour anyway.
    if not _set_vector_default(
            mpc, 'SunDirection',
            unreal.LinearColor(direction.x, direction.y, direction.z, 0.0)):
        return False

    # Alpha is the sun's intensity and it is left where it was. The light actor's intensity is in
    # lux, and an unlit master has no exposure to relate that to, so copying it across would blow
    # every character out the moment someone brightened the level.
    current_colour = _vector_default(mpc, 'SunColor')
    intensity = current_colour.a if current_colour is not None else 1.0

    colour = component.get_editor_property('light_color')
    if not _set_vector_default(
            mpc, 'SunColor',
            unreal.LinearColor(colour.r / 255.0, colour.g / 255.0, colour.b / 255.0, intensity)):
        return False

    EAL.save_loaded_asset(mpc, only_if_is_dirty=False)
    _log('sun synced from %s: direction (%.3f, %.3f, %.3f). Intensity left at %.2f - the light is '
         '%.1f lux and this is not that.'
         % (light.get_actor_label(), direction.x, direction.y, direction.z, intensity,
            float(component.get_editor_property('intensity'))))
    return True
