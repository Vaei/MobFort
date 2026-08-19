# Copyright (c) Jared Taylor. All Rights Reserved

"""Stamps every generated asset with the plugin version that built it, and checks the stamp.

A generated asset is a build output that lives in source control, so nothing about it says which
generator produced it. Content built by one version and shipped beside another reads as a tuning
problem rather than as stale content, and that is the failure this exists to name.

The stamp is package metadata: no node in the graph, no cost at run time, and stripped on cook.

Two values, because they answer different questions.

- The plugin version is what shipped. It is compared against CONTENT_VERSION, the last version whose
  generated output actually had to change, so a patch release that touched no generator does not
  report every asset stale.
- The generator digest covers the scripts that decide what an asset contains. It moves the moment
  they do, which is the in-development drift a version number cannot see, so it is reported as a
  warning rather than a failure.
"""

import hashlib
import json
import os
import re

try:
    import unreal
except ImportError:
    unreal = None


PLUGIN_NAME = 'MobFort'
PLUGIN_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONTENT_ROOT = '/' + PLUGIN_NAME

VERSION_TAG = PLUGIN_NAME + '.Version'
GENERATOR_TAG = PLUGIN_NAME + '.Generator'

# The last plugin version whose generated output changed. Bump this when a generator edit means
# existing content has to be rebuilt; leave it alone for a release that only touched code.
CONTENT_VERSION = '1.1.0'

# The scripts that decide what a generated asset contains. This module is deliberately absent: the
# digest would then change every time the stamping itself was edited.
GENERATOR_SOURCES = (
    'author_fort.py',
)

# Assets a generate must have produced. Anything else under the content root is checked if it
# carries a stamp and merely listed if it does not.
REQUIRED = (
    '/MobFort/M_FortBase',
    '/MobFort/M_FortCharacter',
    '/MobFort/M_FortWeapon',
    '/MobFort/MPC_FortLighting',
    '/MobFort/Functions/MF_FortCharacterFX',
    '/MobFort/Functions/MF_FortCompose',
    '/MobFort/Functions/MF_FortGradientDiffuse',
    '/MobFort/Functions/MF_FortSurface',
    '/MobFort/Functions/MF_FortWeaponDiffuse',
)


_version = None
_digest = None


def _log(message):
    if unreal:
        unreal.log('[{0}] {1}'.format(PLUGIN_NAME, message))
    else:
        print('[{0}] {1}'.format(PLUGIN_NAME, message))


def _log_warning(message):
    if unreal:
        unreal.log_warning('[{0}] {1}'.format(PLUGIN_NAME, message))
    else:
        print('[{0}] WARNING {1}'.format(PLUGIN_NAME, message))


def plugin_version():
    """VersionName out of the .uplugin, which is the single place a version is written."""
    global _version
    if _version is None:
        path = os.path.join(PLUGIN_ROOT, PLUGIN_NAME + '.uplugin')
        with open(path, 'r', encoding='utf-8') as handle:
            _version = str(json.load(handle).get('VersionName', ''))
    return _version


def generator_digest():
    """Short digest of the authoring scripts, over normalised newlines so a checkout cannot move it."""
    global _digest
    if _digest is None:
        accumulator = hashlib.sha1()
        for name in sorted(GENERATOR_SOURCES):
            path = os.path.join(PLUGIN_ROOT, 'Python', name)
            accumulator.update(name.encode('utf-8'))
            with open(path, 'r', encoding='utf-8') as handle:
                accumulator.update(handle.read().replace('\r\n', '\n').encode('utf-8'))
        _digest = accumulator.hexdigest()[:12]
    return _digest


def stamp(asset):
    """Records what built `asset`. Call immediately before saving it."""
    if asset is None:
        return
    unreal.EditorAssetLibrary.set_metadata_tag(asset, VERSION_TAG, plugin_version())
    unreal.EditorAssetLibrary.set_metadata_tag(asset, GENERATOR_TAG, generator_digest())


def read(asset):
    """(version, digest) as stamped on `asset`, either of them None when absent."""
    if asset is None:
        return None, None
    version = unreal.EditorAssetLibrary.get_metadata_tag(asset, VERSION_TAG)
    digest = unreal.EditorAssetLibrary.get_metadata_tag(asset, GENERATOR_TAG)
    return (version or None), (digest or None)


def _parts(version):
    numbers = [int(part) for part in re.findall(r'\d+', version or '')]
    return tuple(numbers + [0] * (3 - len(numbers)))[:3]


def check(paths=None, required=None):
    """Asserts every generated asset was built by a current generator. Returns a list of failures."""
    current = plugin_version()
    expected = generator_digest()
    minimum = _parts(CONTENT_VERSION)

    failures = []

    if _parts(current) < minimum:
        failures.append('CONTENT_VERSION is {0}, later than the {1} in the .uplugin. One of the two '
                        'was bumped and the other was not.'.format(CONTENT_VERSION, current))

    if paths is None:
        paths = unreal.EditorAssetLibrary.list_assets(CONTENT_ROOT, recursive=True,
                                                      include_folder=False)

    demanded = set(REQUIRED if required is None else required)
    missing = set(demanded)
    unstamped = []
    stale = []
    drifted = []
    stamped = 0

    for entry in sorted(paths):
        path = str(entry).split('.')[0]
        asset = unreal.load_asset(path)

        if asset is None:
            continue

        missing.discard(path)
        version, digest = read(asset)

        if version is None:
            if path in demanded:
                failures.append('{0} carries no version stamp, so it predates versioning or was '
                                'built by hand. Run {1} > Generate Materials.'
                                .format(path, PLUGIN_NAME))
            else:
                unstamped.append(path)
            continue

        stamped += 1

        if _parts(version) < minimum:
            stale.append((path, version))
        elif digest != expected:
            drifted.append((path, digest))

    for path in sorted(missing):
        failures.append('{0} is missing. Run {1} > Generate Materials.'.format(path, PLUGIN_NAME))

    # One failure for the lot. A stale generate leaves every asset stale, and sixty lines saying so
    # buries whatever else the contract found.
    if stale:
        oldest = min(stale, key=lambda item: _parts(item[1]))[1]
        failures.append('{0} asset(s) were generated by {1} {2} or older, and {3} changed what a '
                        'generated asset contains, so they no longer match the code that reads '
                        'them. Run {1} > Generate Materials. First: {4}'
                        .format(len(stale), PLUGIN_NAME, oldest, CONTENT_VERSION,
                                ', '.join(path for path, _ in stale[:4])))

    if drifted:
        _log_warning('{0} asset(s) were built by a generator that is not the one on disk (stamped '
                     '{1}, the sources hash to {2}). The scripts have been edited since, so the '
                     'version they carry is right and their contents may not be. Regenerate before '
                     'shipping. First: {3}'
                     .format(len(drifted), drifted[0][1], expected,
                             ', '.join(path for path, _ in drifted[:4])))

    if unstamped:
        _log('  --  {0} asset(s) carry no stamp and are not required to: {1}'
             .format(len(unstamped), ', '.join(unstamped[:4])))

    if not failures and not drifted:
        _log('  ok  {0} asset(s) stamped {1}, generator {2}'.format(stamped, current, expected))

    return failures


def run():
    """Standalone entry point. Returns True when the content is current."""
    _log('Verifying generated content is version {0}'.format(plugin_version()))

    failures = check()
    for failure in failures:
        if unreal:
            unreal.log_error('[{0}] {1}'.format(PLUGIN_NAME, failure))
        else:
            print('[{0}] ERROR {1}'.format(PLUGIN_NAME, failure))

    return not failures


if __name__ == '__main__':
    run()
