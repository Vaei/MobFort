/* Copyright (c) Jared Taylor. All Rights Reserved */

/* The only file that knows which repo this is. assets/docs.css and assets/docs.js are shared
   verbatim with the other plugins; everything specific to MobFort lives here. */

window.DOCS = {
	title: 'MobFort',
	repo: 'https://github.com/Vaei/MobFort',
	icon: 'assets/icon.png',
	imgDir: 'img/',
	footer: 'MobFort is MIT licensed.',

	sections: [
		{
			name: 'Start',
			pages: [
				{ file: 'index.html', label: 'Home', blurb: 'what this is' },
				{ file: 'install.html', label: 'Install', blurb: 'plugin, panorama, sun, first character' }
			]
		},
		{
			name: 'Reference',
			pages: [
				{ file: 'masters.html', label: 'Masters', blurb: 'every parameter on all three' },
				{ file: 'gradients.html', label: 'Gradients', blurb: 'the atlas, and one per character' },
				{ file: 'lighting.html', label: 'Lighting', blurb: 'the sun, indirect, distance' },
				{ file: 'performance.html', label: 'Cost', blurb: 'what each switch gives back' },
				{ file: 'troubleshooting.html', label: 'If it is wrong', blurb: 'symptom to cause' }
			]
		}
	],

	/* Figure slots. Declared once here, placed on a page by id alone.
	   A file that is not in img/ renders as a one-line placeholder instead of a gap,
	   so a page is the same length before and after the art exists. */
	shots: {
		'index.hero': { page: 'index.html', cap: 'One character, unchanged across three very different rooms', file: 'index-hero.png' },
		'index.rim': { page: 'index.html', cap: 'The two rim palettes on the same character', file: 'index-rim.png' },

		'install.menu': { page: 'install.html', cap: 'The Fort menu on the level editor toolbar', file: 'install-menu.png' },
		'install.panorama': { page: 'install.html', cap: 'An equirectangular HDR with its mip chain', file: 'install-panorama.png' },
		'install.instance': { page: 'install.html', cap: 'A character instance with the three textures set', file: 'install-instance.png' },

		'masters.debug': { page: 'masters.html', cap: 'Diffuse, rim, skin, underglow and world normal, side by side', file: 'masters-debug.png' },
		'masters.rim': { page: 'masters.html', cap: 'Rim weighted to the whole silhouette, then to the upper body', file: 'masters-rim-flat.png', compare: 'masters-rim-biased.png', compareLabels: ['Even', 'Biased'] },
		'masters.skin': { page: 'masters.html', cap: 'The same character with SkinAmount 0 and 1', file: 'masters-skin-0.png', compare: 'masters-skin-1.png', compareLabels: ['0', '1'] },
		'masters.pack': { page: 'masters.html', cap: 'BaseColor, Normal and CRM with their channels split', file: 'masters-pack.png' },

		'gradients.editor': { page: 'gradients.html', cap: 'GA_FortCharacter open, five rows', file: 'gradients-editor.png' },
		'gradients.falloff': { page: 'gradients.html', cap: 'The same light with a soft ramp and with a placed terminator', file: 'gradients-soft.png', compare: 'gradients-placed.png', compareLabels: ['Soft', 'Placed'] },
		'gradients.atlas': { page: 'gradients.html', cap: 'The baked atlas: one row per gradient', file: 'gradients-atlas.png' },

		'lighting.mpc': { page: 'lighting.html', cap: 'MPC_FortLighting, which is the whole interface', file: 'lighting-mpc.png' },
		'lighting.indirect': { page: 'lighting.html', cap: 'A character in a dark corner, clamps off and on', file: 'lighting-clamp-off.png', compare: 'lighting-clamp-on.png', compareLabels: ['Unclamped', 'Clamped'] },
		'lighting.depth': { page: 'lighting.html', cap: 'The same character near and far, with the distance response', file: 'lighting-depth.png' },

		'performance.stats': { page: 'performance.html', cap: 'Material stats with the preview platform on ES3.1', file: 'performance-stats.png' },
		'performance.verify': { page: 'performance.html', cap: 'Verify Contract passing in the Output Log', file: 'performance-verify.png' },

		'troubleshooting.mirror': { page: 'troubleshooting.html', cap: 'A panorama with no mip chain: a mirror at every roughness', file: 'troubleshooting-mirror.png' },
		'troubleshooting.pink': { page: 'troubleshooting.html', cap: 'Every character fully skin-shaded from unpainted vertex colours', file: 'troubleshooting-pink.png' }
	}
};
