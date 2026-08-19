// Copyright (c) Jared Taylor

#include "MobFortStatics.h"

#include "Components/MeshComponent.h"
#include "Components/PrimitiveComponent.h"
#include "GameFramework/Actor.h"
#include "Materials/MaterialInstanceDynamic.h"

#include UE_INLINE_GENERATED_CPP_BY_NAME(MobFortStatics)

void UMobFortStatics::CreateDynamicMaterials(UPrimitiveComponent* Component,
	TArray<UMaterialInstanceDynamic*>& OutInstances)
{
	OutInstances.Reset();

	if (!Component)
	{
		return;
	}

	const int32 Num = Component->GetNumMaterials();
	OutInstances.Reserve(Num);

	for (int32 Index = 0; Index < Num; ++Index)
	{
		// Reused rather than replaced. A second call otherwise hands back fresh instances holding the
		// material's authored defaults, quietly undoing whatever the first call wrote.
		UMaterialInstanceDynamic* Instance = Cast<UMaterialInstanceDynamic>(
			Component->GetMaterial(Index));

		if (!Instance)
		{
			Instance = Component->CreateAndSetMaterialInstanceDynamic(Index);
		}

		if (Instance)
		{
			OutInstances.Add(Instance);
		}
	}
}

void UMobFortStatics::CreateDynamicMaterialsForActor(AActor* Actor,
	TArray<UMaterialInstanceDynamic*>& OutInstances, const FName MeshTag)
{
	OutInstances.Reset();

	if (!Actor)
	{
		return;
	}

	TInlineComponentArray<UMeshComponent*> Meshes(Actor);
	for (UMeshComponent* Mesh : Meshes)
	{
		if (!Mesh || (!MeshTag.IsNone() && !Mesh->ComponentHasTag(MeshTag)))
		{
			continue;
		}

		TArray<UMaterialInstanceDynamic*> Created;
		CreateDynamicMaterials(Mesh, Created);
		OutInstances.Append(Created);
	}
}

bool UMobFortStatics::SetSky(UMaterialInstanceDynamic* Instance, UTexture* Panorama,
	UTexture* GradientAtlas, const float SpecularScalar)
{
	bool bAny = false;

	if (Panorama)
	{
		bAny |= SetPanorama(Instance, Panorama);
	}

	if (GradientAtlas)
	{
		bAny |= SetGradientAtlas(Instance, GradientAtlas);
	}

	if (SpecularScalar >= 0.f)
	{
		bAny |= SetSpecularScalar(Instance, SpecularScalar);
	}

	return bAny;
}

int32 UMobFortStatics::SetSkyOnAll(const TArray<UMaterialInstanceDynamic*>& Instances,
	UTexture* Panorama, UTexture* GradientAtlas, const float SpecularScalar)
{
	int32 Count = 0;
	for (UMaterialInstanceDynamic* Instance : Instances)
	{
		if (SetSky(Instance, Panorama, GradientAtlas, SpecularScalar))
		{
			++Count;
		}
	}
	return Count;
}

bool UMobFortStatics::SetPanorama(UMaterialInstanceDynamic* Instance, UTexture* Panorama)
{
	return SetTextureIfPresent(Instance, MobFortParams::SpecPanorama, Panorama);
}

bool UMobFortStatics::SetGradientAtlas(UMaterialInstanceDynamic* Instance, UTexture* Atlas)
{
	return SetTextureIfPresent(Instance, MobFortParams::Atlas, Atlas);
}

bool UMobFortStatics::SetSpecularScalar(UMaterialInstanceDynamic* Instance, const float SpecularScalar)
{
	return SetScalarIfPresent(Instance, MobFortParams::SpecularScalar, SpecularScalar);
}

bool UMobFortStatics::SetMaxMip(UMaterialInstanceDynamic* Instance, const float MaxMip)
{
	return SetScalarIfPresent(Instance, MobFortParams::MaxMip, MaxMip);
}

bool UMobFortStatics::SetGradientRow(UMaterialInstanceDynamic* Instance,
	const EMobFortGradientRow Row, const float Index)
{
	return SetScalarIfPresent(Instance, GetGradientRowParameter(Row), Index);
}

bool UMobFortStatics::IsFortMaterial(UMaterialInstanceDynamic* Instance)
{
	UTexture* Unused = nullptr;
	return Instance && Instance->GetTextureParameterValue(MobFortParams::SpecPanorama, Unused);
}

FName UMobFortStatics::GetGradientRowParameter(const EMobFortGradientRow Row)
{
	switch (Row)
	{
	case EMobFortGradientRow::SkinDiffuse:	return MobFortParams::RowSkinDiffuse;
	case EMobFortGradientRow::RimEnemy:		return MobFortParams::RowRimEnemy;
	case EMobFortGradientRow::RimAlly:		return MobFortParams::RowRimAlly;
	case EMobFortGradientRow::Underglow:	return MobFortParams::RowUnderglow;
	case EMobFortGradientRow::Diffuse:
	default:								return MobFortParams::RowDiffuse;
	}
}

bool UMobFortStatics::SetTextureIfPresent(UMaterialInstanceDynamic* Instance, const FName Parameter,
	UTexture* Value)
{
	// Asked for rather than written blind. SetTextureParameterValue on a parameter the material does
	// not declare does nothing and says nothing, so without this every caller of a renamed parameter
	// gets a success it did not have.
	UTexture* Current = nullptr;
	if (!Instance || !Instance->GetTextureParameterValue(Parameter, Current))
	{
		return false;
	}

	if (Current != Value)
	{
		Instance->SetTextureParameterValue(Parameter, Value);
	}
	return true;
}

bool UMobFortStatics::SetScalarIfPresent(UMaterialInstanceDynamic* Instance, const FName Parameter,
	const float Value)
{
	float Current = 0.f;
	if (!Instance || !Instance->GetScalarParameterValue(Parameter, Current))
	{
		return false;
	}

	if (!FMath::IsNearlyEqual(Current, Value))
	{
		Instance->SetScalarParameterValue(Parameter, Value);
	}
	return true;
}
