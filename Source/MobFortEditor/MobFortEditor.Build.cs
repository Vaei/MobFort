// Copyright (c) Jared Taylor

using UnrealBuildTool;

public class MobFortEditor : ModuleRules
{
	public MobFortEditor(ReadOnlyTargetRules Target) : base(Target)
	{
		PCHUsage = ModuleRules.PCHUsageMode.UseExplicitOrSharedPCHs;

		PublicDependencyModuleNames.AddRange(
			new string[]
			{
				"Core",
				"DeveloperSettings",
			}
			);

		PrivateDependencyModuleNames.AddRange(
			new string[]
			{
				"CoreUObject",
				"Engine",
				"Slate",
				"SlateCore",
				"UnrealEd",
				"ContentBrowser",
				"ToolMenus",
				"Projects",
				"Settings",
				"PythonScriptPlugin",
				"AssetRegistry",
				"AssetTools",
				"MobFort",
			}
			);
	}
}
