# Mob Fort <img align="right" width=128, height=128 src="https://github.com/Vaei/MobFort/blob/main/Resources/Icon128.png">

> [!IMPORTANT]
> Three stylized unlit master materials
> <br>Character, weapon and environment
> <br>You author the light instead of inheriting it
> <br>Designed for the lightweight Mobile Forward Rendering pathway

UE5.8+

> [!NOTE]
> Requires [GradientTool](https://github.com/Vaei/GradientTool)

---

> [!CAUTION]
> MobFort has not officially released. Expect bugs, and updates to occur without versioning or changelog reflecting them. Documentation has no images or videos yet. **Come back soon!**

<!-- TODO(image): hero shot - one character unchanged across three very different rooms -->

## Documentation

**[vaei.github.io/MobFort](https://vaei.github.io/MobFort/)**

Or open [`docs/index.html`](docs/index.html) from a clone - it is a static site with no build step and no network, so it works straight off disk.

| | |
|---|---|
| [Install](https://vaei.github.io/MobFort/install.html) | plugin, panorama, sun, your first character |
| [Masters](https://vaei.github.io/MobFort/masters.html) | every parameter on all three |
| [Gradients](https://vaei.github.io/MobFort/gradients.html) | the atlas, and one per character |
| [Lighting](https://vaei.github.io/MobFort/lighting.html) | the sun, indirect, distance |
| [Cost](https://vaei.github.io/MobFort/performance.html) | what each switch gives back, measured |
| [If it is wrong](https://vaei.github.io/MobFort/troubleshooting.html) | symptom to cause |

## What it is

Characters that look like **Valorant** or **Team Fortress 2**. Or better, because Valorant is deliberately holding back.

Riot tuned this model so that nothing about a character competes with spotting one. The restraint *is* the feature there: controlled contrast, tones that never fight the read, no flourish that could be mistaken for movement. If you are not making a tactical shooter you inherit the technique without the constraint, and you can push the gradients, the rim and the skin as far as your art direction wants to go.

Team Fortress 2 is the basis for this shading that Riot built upon - the wrapped falloff and the rim light in particular. Riot rebuilt it for a modern forward renderer and, unusually, wrote down how. This is that write-up implemented in Unreal.

## Resources

> [!NOTE]
> Mobile Forward Rendering suits **many** games, not merely Valorant/TF2 clones
> <br>And these games can look stunningly beautiful and crisp, while retaining ~1000fps in packaged builds

* [Mobile Forward Rendering Guide](https://blog.daftsoftware.com/unreal-perf-maxing/)
  * Includes Convenient Starter Project
* [Valorant Rendering Guide](https://technology.riotgames.com/news/valorant-shaders-and-gameplay-clarity)
  * The foundation for everything here - gradient lambert, panoramic specular, the rim biases, the fake skin
* [Illustrative Rendering in Team Fortress 2](https://steamcdn-a.akamaihd.net/apps/valve/2007/NPAR07_IllustrativeRenderingInTeamFortress2.pdf)
  * Valve, 2007. Where the wrapped falloff and the rim light came from in the first place
* [Gradient Tool Plugin](https://github.com/Vaei/GradientTool)
  * Required. These techniques need gradients
  * UE5 has "Color Ramp" node, but any modification requires modifying the base material - Gradient Tool's gradients can be modified in realtime
* [Forward Render Helper Plugin](https://github.com/Vaei/ForwardRender)
  * Recommended. Ticks the sun into `MPC_FortLighting` for you, and loads the editor in mobile preview
* [MobMaterials Plugin](https://github.com/Vaei/MobMaterials)
  * The world these characters stand in. Lit landscape, surface and foliage masters on the same renderer

## Features

**The maths is not in the graph.** It lives in [`MobFortShading.ush`](Shaders/Public/MobFortShading.ush) and is reached from Custom nodes. A master material is under ten nodes, and you edit the shader rather than dragging wires.

**Nothing you turn off is paid for.** Every feature is gated by a static bool on a material function input, so a disabled one takes its texture taps and its maths out of the shader entirely.

**No recipe, no generate step.** The three masters ship built. The feature set is fixed by the shading model rather than by what a given project wants, so there is nothing to author before you can use them.

### Lighting you control, not lighting you receive

- **A gradient in place of the diffuse falloff.** Drag stops to place the highlight, the mid tone, the core shadow and both transitions. It re-bakes live, so no material recompiles while you tune the look
- **A pre-blurred HDR panorama in place of every reflection in the scene.** One tap at a mip chosen from roughness - no analytic highlights anywhere, so a rough surface costs exactly what a shiny one does
- **No ambient term at all.** The gradient never reaches black, so nothing ever goes fully dark and no corner of a level can swallow a character
- **Areas are dialled, not lit.** Two clamped indirect scales stand in for a lighting cache, with specular darkening faster than diffuse - so a shadowed character does not read as a chrome cutout

### Characters that stay themselves

- **A rim that describes the silhouette instead of outlining it**, weighted toward up-facing surfaces and the upper body so it reads as light rather than as an overlay. Two palettes, picked per instance - ally and enemy, faction, status, whatever you need the distinction to be
- **Fake skin**: a redder falloff row blended by vertex paint, plus a wax underglow with a specular-like grazing response that strengthens exactly where the direct light gives up
- **A distance response** that widens the rim and lifts the lit term as a character gets small on screen, clamped at both ends so nobody turns into a lamp
- **Gradients per character.** The atlas is a texture parameter and every row index is a scalar, so a character carries its own palette without forking the plugin - and four rows still cost one sampler

### Built for the mobile forward path

- **3 samplers, whatever is switched on.** The surface taps share the world wrap group; the atlas and the panorama take one each. Nowhere near the 16 the platform allows
- **Cavity, never ambient occlusion.** Micro shadowing multiplies base colour and specular, so the same CRM pack serves a lit master in the same project without doubling with the renderer's own occlusion
- **Emissive rides the albedo's alpha**, so a glowing element costs no texture and no sampler
- **Debug views** for the diffuse gradient, the rim, the skin and the underglow masks - because a rim weighted to the wrong half of a body looks exactly like a rim weighted correctly until you see them side by side
- **The claims are asserted, not stated.** **Fort &rarr; Verify Contract** builds an instance per feature and checks all 47 of them against the documentation

## Quick start

1. Enable the plugin, and [GradientTool](https://github.com/Vaei/GradientTool).
2. Point `SpecPanorama` at an equirectangular HDR with a mip chain.
3. **Fort &rarr; Sync Sun From Directional Light**.
4. Instance `M_FortCharacter`, set `BaseColor` / `Normal` / `CRM`, tick `bUseCRMTexture`.

Duplicate that instance and tick `bEnemy` for the second rim palette. Everything else is on the [documentation site](https://vaei.github.io/MobFort/).

## License

MIT. Documentation ships IBM Plex under the SIL Open Font License 1.1 - see `docs/assets/fonts/OFL.txt`.
