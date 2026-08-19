// Copyright (c) Jared Taylor

#pragma once

#include "CoreMinimal.h"

/**
 * Custom primitive data layout, shared by the component that writes it and the masters that read it.
 *
 * The same indices are authored into MF_FortSurface by author_fort.py, and nothing checks the two
 * agree: a mismatch is a character who dries off from the neck down, not an error.
 *
 * Per primitive rather than per instance because a level is two character material instances and a
 * hundred characters, and how wet each one is has to differ without any of them owning a material.
 *
 * The slots start at 6 because the surface masters a character's props and armour are made of claim
 * 0 through 5, and the component writes every mesh on the owner. Overlapping them would drive a
 * prop's tint from the waterline, which reads as a bug in the prop.
 */
namespace MobFortData
{
	/** Where the waterline sits, as a fraction of the primitive's own bounds. 0 is dry. */
	static constexpr int32 WetLine = 6;

	/** How wet the surface below the line is. */
	static constexpr int32 Wetness = 7;

	/**
	 * How much darker this primitive's surroundings are than the collection says, 0 to 1.
	 *
	 * Darkening rather than a scale, because unset custom primitive data reads as zero: a scale
	 * would default every character to black, and a darkening defaults them to unaffected.
	 */
	static constexpr int32 LightDarken = 8;

	/** One past the last slot claimed here. */
	static constexpr int32 Num = 9;
}
