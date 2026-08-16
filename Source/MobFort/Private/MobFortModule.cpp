// Copyright (c) Jared Taylor

#include "MobFortModule.h"

#include "Interfaces/IPluginManager.h"
#include "Misc/Paths.h"
#include "ShaderCore.h"

#define LOCTEXT_NAMESPACE "MobFort"

void FMobFortModule::StartupModule()
{
	// The masters reach their maths through Custom nodes that include /MobFort/Public/*.ush, so the
	// virtual directory has to exist before anything compiles a material. Hence PostConfigInit
	// rather than Default: a material can be pulled in by a startup asset, and an include that
	// resolves to nothing is stripped from the cached data, which surfaces as an undeclared
	// identifier rather than a missing file.
	const TSharedPtr<IPlugin> Plugin = IPluginManager::Get().FindPlugin(TEXT("MobFort"));
	if (Plugin.IsValid())
	{
		const FString PluginRoot = FPaths::ConvertRelativePathToFull(Plugin->GetBaseDir());
		AddShaderSourceDirectoryMapping(TEXT("/MobFort"), FPaths::Combine(PluginRoot, TEXT("Shaders")));
	}
}

#undef LOCTEXT_NAMESPACE

IMPLEMENT_MODULE(FMobFortModule, MobFort)
