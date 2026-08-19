// Copyright (c) Jared Taylor

#include "MobFortEditor.h"

#include "MobFortEditorStyle.h"
#include "MobFortEditorUserSettings.h"

#include "AssetRegistry/ARFilter.h"
#include "AssetRegistry/AssetRegistryModule.h"
#include "AssetToolsModule.h"
#include "Editor.h"
#include "Engine/DirectionalLight.h"
#include "EngineUtils.h"
#include "Framework/MultiBox/MultiBoxBuilder.h"
#include "Framework/Notifications/NotificationManager.h"
#include "IAssetTools.h"
#include "IPythonScriptPlugin.h"
#include "ContentBrowserModule.h"
#include "IContentBrowserSingleton.h"
#include "Engine/TextureCube.h"
#include "ISettingsModule.h"
#include "Interfaces/IPluginManager.h"
#include "Misc/PackageName.h"
#include "Misc/Paths.h"
#include "Styling/AppStyle.h"
#include "Subsystems/AssetEditorSubsystem.h"
#include "ToolMenus.h"
#include "Widgets/Notifications/SNotificationList.h"
#include "Widgets/Text/STextBlock.h"

#define LOCTEXT_NAMESPACE "MobFortEditor"

namespace MobFort
{
	static const TCHAR* LightingCollection = TEXT("/MobFort/MPC_FortLighting.MPC_FortLighting");
	static const TCHAR* CharacterAtlas = TEXT("/MobFort/Gradients/GA_FortCharacter.GA_FortCharacter");

	static const TCHAR* Masters[] =
	{
		TEXT("/MobFort/M_FortCharacter.M_FortCharacter"),
		TEXT("/MobFort/M_FortWeapon.M_FortWeapon"),
		TEXT("/MobFort/M_FortBase.M_FortBase"),
	};

	/** The first directional light in the open level, or null. */
	static ADirectionalLight* FindSun()
	{
		if (!GEditor)
		{
			return nullptr;
		}

		UWorld* World = GEditor->GetEditorWorldContext().World();
		if (!World)
		{
			return nullptr;
		}

		for (TActorIterator<ADirectionalLight> It(World); It; ++It)
		{
			return *It;
		}
		return nullptr;
	}
}

void FMobFortEditorModule::StartupModule()
{
	FMobFortEditorStyle::Register();

	if (UToolMenus::IsToolMenuUIEnabled())
	{
		UToolMenus::RegisterStartupCallback(FSimpleMulticastDelegate::FDelegate::CreateRaw(
			this, &FMobFortEditorModule::RegisterMenus));
	}
}

void FMobFortEditorModule::ShutdownModule()
{
	UToolMenus::UnRegisterStartupCallback(this);
	UToolMenus::UnregisterOwner(this);
	FMobFortEditorStyle::Unregister();
}

namespace
{
	/** The fixed left to right order of the Mob toolbar buttons. A button that is not listed sorts to the end. */
	int32 MobToolbarOrder(const FName EntryName)
	{
		static const FName Order[] =
		{
			TEXT("WorldMenu"),
			TEXT("MobLightsMenu"),
			TEXT("MobWaterMenu"),
			TEXT("FortMenu"),
			TEXT("MatMenu"),
		};

		for (int32 Index = 0; Index < UE_ARRAY_COUNT(Order); ++Index)
		{
			if (Order[Index] == EntryName)
			{
				return Index;
			}
		}

		return MAX_int32;
	}

	// Every Mob plugin installs this same comparison on the shared section, so the order holds whichever of them
	// are installed and whatever order their modules load in.
	bool MobToolbarOrderLess(const FToolMenuEntry& A, const FToolMenuEntry& B, const FToolMenuContext&)
	{
		return MobToolbarOrder(A.Name) < MobToolbarOrder(B.Name);
	}
}

void FMobFortEditorModule::RegisterMenus()
{
	FToolMenuOwnerScoped OwnerScoped(this);

	UToolMenu* ToolBar = UToolMenus::Get()->ExtendMenu(TEXT("LevelEditor.LevelEditorToolBar.PlayToolBar"));
	if (!ToolBar)
	{
		return;
	}

	FToolMenuEntry Entry = FToolMenuEntry::InitComboButton(
		TEXT("FortMenu"),
		FUIAction(
			FExecuteAction(),
			FCanExecuteAction(),
			FIsActionChecked(),
			FIsActionButtonVisible::CreateStatic(&FMobFortEditorModule::IsToolbarMenuEnabled)),
		FOnGetContent::CreateRaw(this, &FMobFortEditorModule::BuildMenu),
		LOCTEXT("FortToolbar", "Fort"),
		LOCTEXT("FortToolbarTip", "Character shading tools"),
		FSlateIcon(FMobFortEditorStyle::GetStyleSetName(), FMobFortEditorStyle::GetMenuIconName())
	);

	// The style that gives a toolbar button its label beside the icon.
	Entry.StyleNameOverride = TEXT("CalloutToolbar");

	FToolMenuSection& Section = ToolBar->FindOrAddSection(TEXT("MobTools"));
	Section.Sorter = FToolMenuSectionSorter::CreateStatic(&MobToolbarOrderLess);
	Section.AddEntry(Entry);
}

void FMobFortEditorModule::FindGradientAssets(TArray<FAssetData>& OutAssets)
{
	const FAssetRegistryModule& Registry =
		FModuleManager::LoadModuleChecked<FAssetRegistryModule>(TEXT("AssetRegistry"));

	// Matched by class name rather than by static class, so the editor module does not have to
	// depend on GradientTool to list what it can open.
	FARFilter Filter;
	Filter.ClassPaths.Add(FTopLevelAssetPath(TEXT("/Script/GradientTool"), TEXT("GradientAsset")));
	Filter.bRecursiveClasses = true;
	Registry.Get().GetAssets(Filter, OutAssets);

	OutAssets.Sort([](const FAssetData& A, const FAssetData& B)
	{
		return A.AssetName.LexicalLess(B.AssetName);
	});
}

TSharedRef<SWidget> FMobFortEditorModule::BuildMenu()
{
	FMenuBuilder Menu(true, nullptr);

	// Greyed out entries say why in their own tooltip: a disabled entry with the same text as an
	// enabled one only tells you it is disabled, which is the part already visible.
	auto Reason = [](const FText& Tip, FText (*Why)()) -> TAttribute<FText>
	{
		return TAttribute<FText>::CreateLambda([Tip, Why]
		{
			const FText Blocked = Why();
			return Blocked.IsEmpty() ? Tip
				: FText::Format(LOCTEXT("Blocked", "{0}\n\n{1}"), Tip, Blocked);
		});
	};

	Menu.BeginSection(TEXT("FortGradients"), LOCTEXT("GradientsSection", "Gradients"));
	Menu.AddMenuEntry(
		LOCTEXT("NewAtlas", "New Character Atlas..."),
		LOCTEXT("NewAtlasTip",
			"Copies GA_FortCharacter so a character can have gradients of its own. Point the "
			"instance's Atlas parameter at the copy's baked texture - the sibling T_ asset, not the "
			"Gradient asset. Keep the row order and the Row parameters need no touching."),
		FSlateIcon(FAppStyle::GetAppStyleSetName(), TEXT("Icons.Duplicate")),
		FUIAction(
			FExecuteAction::CreateStatic(&FMobFortEditorModule::NewCharacterAtlas),
			FCanExecuteAction::CreateStatic(&FMobFortEditorModule::CanMakeAtlas)));

	TArray<FAssetData> Atlases;
	FindGradientAssets(Atlases);
	for (const FAssetData& Asset : Atlases)
	{
		const FSoftObjectPath Path = Asset.ToSoftObjectPath();
		Menu.AddMenuEntry(
			FText::Format(LOCTEXT("OpenAtlas", "Open {0}"), FText::FromName(Asset.AssetName)),
			LOCTEXT("OpenAtlasTip",
				"Drag stops and the atlas re-bakes as you go, so every material reading it updates "
				"live and none of them has to be recompiled."),
			FSlateIcon(FAppStyle::GetAppStyleSetName(), TEXT("Icons.Edit")),
			FUIAction(FExecuteAction::CreateStatic(&FMobFortEditorModule::OpenAsset, Path)));
	}

	if (Atlases.Num() == 0)
	{
		Menu.AddWidget(
			SNew(STextBlock)
			.Text(LOCTEXT("NoAtlases", "No gradient atlases found."))
			.ColorAndOpacity(FSlateColor::UseSubduedForeground())
			.Margin(FMargin(12.f, 4.f)),
			FText::GetEmpty());
	}
	Menu.EndSection();

	Menu.BeginSection(TEXT("FortLighting"), LOCTEXT("LightingSection", "Lighting"));
	Menu.AddMenuEntry(
		LOCTEXT("SyncSun", "Sync Sun From Directional Light"),
		Reason(LOCTEXT("SyncSunTip",
			"Writes the level's directional light into MPC_FortLighting as the direction and colour "
			"the masters shade against. Nothing in this plugin reads a light actor, so until this "
			"runs the characters are lit by whatever the collection shipped with and rotating the "
			"sun changes nothing on them.\n\n"
			"One shot, and it saves the collection. Drive it from the level Blueprint instead if "
			"the sun moves during play."),
			&FMobFortEditorModule::SyncSunReason),
		FSlateIcon(FAppStyle::GetAppStyleSetName(), TEXT("ClassIcon.DirectionalLight")),
		FUIAction(
			FExecuteAction::CreateStatic(&FMobFortEditorModule::SyncSun),
			FCanExecuteAction::CreateStatic(&FMobFortEditorModule::CanSyncSun)));

	Menu.AddMenuEntry(
		LOCTEXT("OpenLighting", "Open MPC_FortLighting"),
		LOCTEXT("OpenLightingTip",
			"The sun, the indirect scales and the distance compensation. Scrub Indirect and every "
			"character follows live, which is the fastest way to see whether a value is clamped "
			"somewhere it should not be."),
		FSlateIcon(FAppStyle::GetAppStyleSetName(), TEXT("ClassIcon.MaterialParameterCollection")),
		FUIAction(
			FExecuteAction::CreateStatic(&FMobFortEditorModule::OpenAsset,
				FSoftObjectPath(MobFort::LightingCollection)),
			FCanExecuteAction::CreateStatic(&FMobFortEditorModule::AssetExists,
				FSoftObjectPath(MobFort::LightingCollection))));
	Menu.EndSection();

	Menu.BeginSection(TEXT("FortMasters"), LOCTEXT("MastersSection", "Masters"));
	for (const TCHAR* Master : MobFort::Masters)
	{
		const FSoftObjectPath Path(Master);
		Menu.AddMenuEntry(
			FText::Format(LOCTEXT("OpenMaster", "Open {0}"), FText::FromString(Path.GetAssetName())),
			LOCTEXT("OpenMasterTip",
				"The graph is thin on purpose - the maths is in MobFortShading.ush, reached from the "
				"Custom nodes. Edit the ush, not the graph."),
			FSlateIcon(FAppStyle::GetAppStyleSetName(), TEXT("ClassIcon.Material")),
			FUIAction(
				FExecuteAction::CreateStatic(&FMobFortEditorModule::OpenAsset, Path),
				FCanExecuteAction::CreateStatic(&FMobFortEditorModule::AssetExists, Path)));
	}
	Menu.EndSection();

	Menu.BeginSection(TEXT("FortBuild"), LOCTEXT("BuildSection", "Build"));
	Menu.AddMenuEntry(
		LOCTEXT("Verify", "Verify Contract"),
		LOCTEXT("VerifyTip",
			"Builds an instance per feature and asserts what the design claims: that dropping a "
			"response gives back its texture tap and its sampler, that debug costs nothing when "
			"off, that the gradient rows share one sampler, that every master still writes only to "
			"emissive. Results go to the Output Log.\n\n"
			"A permutation nobody has compiled before reports zero and fails rather than being "
			"skipped, because that is indistinguishable from one that failed to compile - which is "
			"exactly where a default-off branch hides a broken sampler type. On a cold derived data "
			"cache, run it a second time before believing it."),
		FSlateIcon(FAppStyle::GetAppStyleSetName(), TEXT("Icons.Check")),
		FUIAction(FExecuteAction::CreateStatic(&FMobFortEditorModule::Verify)));

	Menu.AddMenuEntry(
		LOCTEXT("Rebuild", "Rebuild Materials"),
		LOCTEXT("RebuildTip",
			"Re-authors every function, master and instance from author_fort.py, then saves. Needed "
			"after editing the builder or the gradient row list; not needed after editing a ush, "
			"which only wants a shader recompile.\n\n"
			"Each asset is emptied and rebuilt in place, so instances keep their references and "
			"their overrides. Anything hand-edited in these graphs is lost."),
		FSlateIcon(FAppStyle::GetAppStyleSetName(), TEXT("Icons.Refresh")),
		FUIAction(FExecuteAction::CreateStatic(&FMobFortEditorModule::RebuildMaterials)));

	Menu.AddMenuEntry(
		LOCTEXT("Panorama", "Panorama From Cubemap"),
		LOCTEXT("PanoramaTip",
			"Bakes the cubemaps selected in the content browser into the long/lat images the "
			"specular reads, one beside each cube in a Panorama folder.\n\n"
			"A cubemap cannot be assigned to SpecPanorama and an .hdr imports as one whatever the "
			"import settings say, which is what this is for. The bake goes through a material that "
			"samples the cube, so the seam lands where FortPanoramaUV expects it rather than where "
			"the source file happened to put it.\n\n"
			"Mips are generated, because roughness picks one: without a chain every surface is a "
			"mirror at every roughness and nothing says so. The Output Log reports the MaxMip to "
			"set on the instance."),
		FSlateIcon(FAppStyle::GetAppStyleSetName(), TEXT("ClassIcon.TextureCube")),
		FUIAction(
			FExecuteAction::CreateStatic(&FMobFortEditorModule::ConvertSelectedToPanorama),
			FCanExecuteAction::CreateStatic(&FMobFortEditorModule::HasCubemapSelected)));
	Menu.EndSection();

	Menu.BeginSection(TEXT("FortSettings"), LOCTEXT("SettingsSection", "Settings"));
	Menu.AddMenuEntry(
		LOCTEXT("EditorSettings", "Editor Preferences"),
		LOCTEXT("EditorSettingsTip", "Per-developer settings for this plugin. Not checked in."),
		FSlateIcon(FAppStyle::GetAppStyleSetName(), TEXT("Icons.Toolbar.Settings")),
		FUIAction(FExecuteAction::CreateStatic(&FMobFortEditorModule::OpenSettings)));

	Menu.AddMenuEntry(
		LOCTEXT("HideMenu", "Hide This Menu"),
		LOCTEXT("HideMenuTip",
			"Removes the Fort button from your toolbar. Turn it back on under Editor Preferences, "
			"Plugins, Mob Fort Editor."),
		FSlateIcon(FAppStyle::GetAppStyleSetName(), TEXT("Icons.Visibility")),
		FUIAction(FExecuteAction::CreateStatic(&FMobFortEditorModule::HideToolbarMenu)));
	Menu.EndSection();

	if (!IsPythonAvailable())
	{
		Menu.BeginSection(TEXT("FortPython"));
		Menu.AddWidget(
			SNew(STextBlock)
			.Text(LOCTEXT("NoPython",
				"Rebuilding and verifying need the Python Editor Script Plugin."))
			.ColorAndOpacity(FSlateColor::UseSubduedForeground())
			.Margin(FMargin(12.f, 4.f)),
			FText::GetEmpty());
		Menu.EndSection();
	}

	return Menu.MakeWidget();
}

bool FMobFortEditorModule::IsPythonAvailable()
{
	return IPythonScriptPlugin::Get() && IPythonScriptPlugin::Get()->IsPythonAvailable();
}

bool FMobFortEditorModule::RunPython(const FString& Snippet, const FText& DoneMessage)
{
	if (!IsPythonAvailable())
	{
		return false;
	}

	const TSharedPtr<IPlugin> Plugin = IPluginManager::Get().FindPlugin(TEXT("MobFort"));
	if (!Plugin.IsValid())
	{
		return false;
	}

	const FString ScriptDir = FPaths::Combine(
		FPaths::ConvertRelativePathToFull(Plugin->GetBaseDir()), TEXT("Python")).Replace(TEXT("\\"), TEXT("/"));

	const FString Command = FString::Printf(
		TEXT("import sys\n")
		TEXT("p = r'%s'\n")
		TEXT("sys.path.append(p) if p not in sys.path else None\n")
		TEXT("%s\n"), *ScriptDir, *Snippet);

	const bool bOk = IPythonScriptPlugin::Get()->ExecPythonCommand(*Command);

	FNotificationInfo Info(bOk ? DoneMessage
		: LOCTEXT("PythonFailed", "Fort: failed. See the Output Log."));
	Info.ExpireDuration = bOk ? 4.f : 8.f;
	if (const TSharedPtr<SNotificationItem> Item = FSlateNotificationManager::Get().AddNotification(Info))
	{
		Item->SetCompletionState(bOk ? SNotificationItem::CS_Success : SNotificationItem::CS_Fail);
	}
	return bOk;
}

void FMobFortEditorModule::RebuildMaterials()
{
	RunPython(
		TEXT("import importlib, author_fort; importlib.reload(author_fort); author_fort.build_all()"),
		LOCTEXT("RebuildDone", "Fort: materials rebuilt. See the Output Log."));
}

void FMobFortEditorModule::Verify()
{
	RunPython(
		TEXT("import importlib, fort_verify; importlib.reload(fort_verify); fort_verify.run()"),
		LOCTEXT("VerifyDone", "Fort: verification finished. See the Output Log."));
}

void FMobFortEditorModule::ConvertSelectedToPanorama()
{
	RunPython(
		TEXT("import importlib, fort_panorama; importlib.reload(fort_panorama); ")
		TEXT("fort_panorama.convert_selected()"),
		LOCTEXT("PanoramaDone", "Fort: panoramas baked. See the Output Log for their MaxMip."));
}

bool FMobFortEditorModule::HasCubemapSelected()
{
	const FContentBrowserModule* ContentBrowser =
		FModuleManager::GetModulePtr<FContentBrowserModule>(TEXT("ContentBrowser"));

	if (!ContentBrowser)
	{
		return false;
	}

	TArray<FAssetData> Selected;
	ContentBrowser->Get().GetSelectedAssets(Selected);

	// The class name rather than the asset: asking for the object would load every cube the browser
	// is showing, every time the menu is opened.
	for (const FAssetData& Asset : Selected)
	{
		if (Asset.AssetClassPath == UTextureCube::StaticClass()->GetClassPathName())
		{
			return true;
		}
	}

	return false;
}

bool FMobFortEditorModule::CanMakeAtlas()
{
	return FPackageName::DoesPackageExist(FSoftObjectPath(MobFort::CharacterAtlas).GetLongPackageName());
}

void FMobFortEditorModule::NewCharacterAtlas()
{
	UObject* Source = FSoftObjectPath(MobFort::CharacterAtlas).TryLoad();
	if (!Source)
	{
		return;
	}

	// With a dialog, because where a character's gradients live is the project's business and this
	// plugin has no idea where that is.
	const FAssetToolsModule& AssetTools =
		FModuleManager::LoadModuleChecked<FAssetToolsModule>(TEXT("AssetTools"));
	AssetTools.Get().DuplicateAssetWithDialog(
		TEXT("GA_FortCharacter"), TEXT("/Game"), Source);
}

bool FMobFortEditorModule::CanSyncSun()
{
	return IsPythonAvailable() && MobFort::FindSun() != nullptr
		&& AssetExists(FSoftObjectPath(MobFort::LightingCollection));
}

FText FMobFortEditorModule::SyncSunReason()
{
	if (!IsPythonAvailable())
	{
		return LOCTEXT("SyncNoPython", "This needs the Python Editor Script Plugin.");
	}
	if (!AssetExists(FSoftObjectPath(MobFort::LightingCollection)))
	{
		return LOCTEXT("SyncNoCollection", "MPC_FortLighting is missing. Rebuild Materials first.");
	}
	if (!MobFort::FindSun())
	{
		return LOCTEXT("SyncNoLight", "There is no directional light in this level.");
	}
	return FText::GetEmpty();
}

void FMobFortEditorModule::SyncSun()
{
	const ADirectionalLight* Sun = MobFort::FindSun();
	if (!Sun)
	{
		return;
	}

	RunPython(FString::Printf(
		TEXT("import importlib, fort_lighting; importlib.reload(fort_lighting); ")
		TEXT("fort_lighting.sync_sun(r'%s')"), *Sun->GetPathName()),
		LOCTEXT("SyncDone", "Fort: sun written to MPC_FortLighting."));
}

bool FMobFortEditorModule::IsToolbarMenuEnabled()
{
	return GetDefault<UMobFortEditorUserSettings>()->bShowToolbarMenu;
}

void FMobFortEditorModule::HideToolbarMenu()
{
	UMobFortEditorUserSettings* Settings = GetMutableDefault<UMobFortEditorUserSettings>();
	Settings->bShowToolbarMenu = false;
	Settings->SaveConfig();
}

void FMobFortEditorModule::OpenSettings()
{
	const UDeveloperSettings* Settings = GetDefault<UMobFortEditorUserSettings>();
	if (ISettingsModule* SettingsModule = FModuleManager::GetModulePtr<ISettingsModule>(TEXT("Settings")))
	{
		// Asked of the settings object rather than spelled out. A section is registered under the
		// class name, not the display name, so naming it by hand opens the window on whatever was
		// last shown, which reads as the menu entry doing nothing.
		SettingsModule->ShowViewer(Settings->GetContainerName(), Settings->GetCategoryName(),
			Settings->GetSectionName());
	}
}

bool FMobFortEditorModule::AssetExists(FSoftObjectPath Path)
{
	return FPackageName::DoesPackageExist(Path.GetLongPackageName());
}

void FMobFortEditorModule::OpenAsset(FSoftObjectPath Path)
{
	if (UObject* Asset = Path.TryLoad(); Asset && GEditor)
	{
		GEditor->GetEditorSubsystem<UAssetEditorSubsystem>()->OpenEditorForAsset(Asset);
	}
}

#undef LOCTEXT_NAMESPACE

IMPLEMENT_MODULE(FMobFortEditorModule, MobFortEditor)
