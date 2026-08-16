// Copyright (c) Jared Taylor

#pragma once

#include "CoreMinimal.h"
#include "AssetRegistry/AssetData.h"
#include "Modules/ModuleManager.h"
#include "UObject/SoftObjectPath.h"

class SWidget;

class FMobFortEditorModule final : public IModuleInterface
{
public:
	virtual void StartupModule() override;
	virtual void ShutdownModule() override;

private:
	void RegisterMenus();
	TSharedRef<SWidget> BuildMenu();

	/** Every Gradient asset in the project, sorted by name. */
	static void FindGradientAssets(TArray<FAssetData>& OutAssets);

	/** Rebuilds every master, function and instance from author_fort.py. */
	static void RebuildMaterials();

	/** Asserts what the design claims: what each feature costs, and what turning it off gives back. */
	static void Verify();

	/** Copies the shipped atlas so a character can have gradients of its own. */
	static void NewCharacterAtlas();
	static bool CanMakeAtlas();

	/**
	 * Writes the level's directional light into MPC_FortLighting.
	 *
	 * Nothing else in this plugin reads a light actor, so until this runs the materials are lit by
	 * whatever direction the collection shipped with, and rotating the level's sun changes nothing.
	 */
	static void SyncSun();
	static bool CanSyncSun();
	static FText SyncSunReason();

	/** Runs a snippet against the plugin's Python directory. */
	static bool RunPython(const FString& Snippet, const FText& DoneMessage);

	/** Whether the toolbar button is shown. Per developer, not checked in. */
	static bool IsToolbarMenuEnabled();
	static void HideToolbarMenu();
	static void OpenSettings();

	/** Opens whatever is at a path in its own editor. */
	static void OpenAsset(FSoftObjectPath Path);
	static bool AssetExists(FSoftObjectPath Path);

	/** Python is only needed to rebuild and verify; the shipped materials work without it. */
	static bool IsPythonAvailable();
};
