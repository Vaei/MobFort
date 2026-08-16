// Copyright (c) Jared Taylor

#pragma once

#include "CoreMinimal.h"

class FSlateStyleSet;

/** Slate brushes for the MobFort editor UI, sourced from the plugin's Resources folder. */
class MOBFORTEDITOR_API FMobFortEditorStyle
{
public:
	static void Register();
	static void Unregister();

	static FName GetStyleSetName();

	/** The plugin icon, sized for a toolbar entry. */
	static FName GetMenuIconName() { return TEXT("Fort.MenuIcon"); }

private:
	static TSharedPtr<FSlateStyleSet> StyleSet;
};
