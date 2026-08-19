// Copyright (c) Jared Taylor

#pragma once

#include "CoreMinimal.h"
#include "Kismet/BlueprintFunctionLibrary.h"
#include "MobFortStatics.generated.h"

class UMaterialInstanceDynamic;
class UPrimitiveComponent;
class UTexture;

/**
 * The parameter names the masters declare, in one place.
 *
 * A caller writing "SpecPanorama" as a literal is a rename away from a silent no-op, because setting
 * a parameter a material does not have is not an error anywhere in the engine. Everything that writes
 * a MobFort material goes through the helpers below rather than through these directly.
 */
namespace MobFortParams
{
	/** The long/lat image a character reflects. */
	static const FName SpecPanorama = TEXT("SpecPanorama");

	/** Mip a roughness of 1 reads, which is the length of the panorama's chain. */
	static const FName MaxMip = TEXT("MaxMip");

	/** Overall reflection strength. */
	static const FName SpecularScalar = TEXT("SpecularScalar");

	/** The gradient atlas the diffuse falloff, the skin ramps and both rims are read from. */
	static const FName Atlas = TEXT("Atlas");

	/** Which row of that atlas each response takes. */
	static const FName RowDiffuse = TEXT("RowDiffuse");
	static const FName RowSkinDiffuse = TEXT("RowSkinDiffuse");
	static const FName RowRimEnemy = TEXT("RowRimEnemy");
	static const FName RowRimAlly = TEXT("RowRimAlly");
	static const FName RowUnderglow = TEXT("RowUnderglow");
}

/** Which gradient a row index is being set for. */
UENUM(BlueprintType)
enum class EMobFortGradientRow : uint8
{
	Diffuse			UMETA(ToolTip="The lit-to-unlit falloff every surface reads"),
	SkinDiffuse		UMETA(ToolTip="The same, for skin"),
	RimEnemy		UMETA(ToolTip="The team rim on an enemy"),
	RimAlly			UMETA(ToolTip="The team rim on an ally"),
	Underglow		UMETA(ToolTip="The warmth under skin at grazing angles"),
};

/**
 * Making a character's materials dynamic, and writing to them afterwards.
 *
 * MobFort's masters are authored so a level is two character instances and a hundred characters, and
 * anything that differs per character is custom primitive data for that reason. What is left is the
 * handful of things that differ per *scene*: which sky is being reflected, how hard, and through
 * which gradients. Those are the same value for everyone on screen, and a dynamic instance per
 * character is how they reach a skeletal mesh at all - it has no cheaper hook, and it does not
 * instance across draws the way a static mesh would, so the cost of one is a uniform buffer.
 *
 * The names live in MobFortParams and nothing outside this file should use them. Writing a parameter
 * a material does not declare is silently ignored by the engine, so a typo or a rename is a value
 * that never arrives and never complains; every setter here reports whether it landed.
 */
UCLASS()
class MOBFORT_API UMobFortStatics : public UBlueprintFunctionLibrary
{
	GENERATED_BODY()

public:
	//~ Creation ---------------------------------------------------------------------------------

	/**
	 * Makes every material slot on a component dynamic and hands them back.
	 *
	 * Already-dynamic slots are reused rather than replaced, so calling this twice does not throw
	 * away the values the first call wrote.
	 */
	UFUNCTION(BlueprintCallable, Category="MobFort|Material")
	static void CreateDynamicMaterials(UPrimitiveComponent* Component,
		TArray<UMaterialInstanceDynamic*>& OutInstances);

	/**
	 * The same for every mesh on an actor: the character, the weapon in their hand, the sheath on
	 * their back.
	 *
	 * With a tag, only meshes carrying it are touched. Without, every mesh is - including any a
	 * project attaches for reasons of its own, which is usually not what is wanted on a character.
	 */
	UFUNCTION(BlueprintCallable, Category="MobFort|Material")
	static void CreateDynamicMaterialsForActor(AActor* Actor,
		TArray<UMaterialInstanceDynamic*>& OutInstances, FName MeshTag = NAME_None);

	//~ The scene --------------------------------------------------------------------------------

	/**
	 * Puts an instance under a sky: what it reflects, through which gradients, and how hard.
	 *
	 * Null textures and a negative scalar are each left alone rather than cleared, so a caller that
	 * only knows half the answer can say so. @return true if anything landed.
	 */
	UFUNCTION(BlueprintCallable, Category="MobFort|Material")
	static bool SetSky(UMaterialInstanceDynamic* Instance, UTexture* Panorama, UTexture* GradientAtlas,
		float SpecularScalar = -1.f);

	/** The same, across a set. @return how many instances took at least one value. */
	UFUNCTION(BlueprintCallable, Category="MobFort|Material")
	static int32 SetSkyOnAll(const TArray<UMaterialInstanceDynamic*>& Instances, UTexture* Panorama,
		UTexture* GradientAtlas, float SpecularScalar = -1.f);

	//~ One at a time ----------------------------------------------------------------------------

	/** @return false when the material does not declare the parameter, which is how a weapon says it is not a character. */
	UFUNCTION(BlueprintCallable, Category="MobFort|Material")
	static bool SetPanorama(UMaterialInstanceDynamic* Instance, UTexture* Panorama);

	UFUNCTION(BlueprintCallable, Category="MobFort|Material")
	static bool SetGradientAtlas(UMaterialInstanceDynamic* Instance, UTexture* Atlas);

	UFUNCTION(BlueprintCallable, Category="MobFort|Material")
	static bool SetSpecularScalar(UMaterialInstanceDynamic* Instance, float SpecularScalar);

	/** How long the panorama's mip chain is. Set it with the panorama or a rough surface reads a sharp sky. */
	UFUNCTION(BlueprintCallable, Category="MobFort|Material")
	static bool SetMaxMip(UMaterialInstanceDynamic* Instance, float MaxMip);

	/**
	 * Moves one response to a different row of the atlas.
	 *
	 * Whole numbers only: a fraction lands between two rows and the filter blends them.
	 */
	UFUNCTION(BlueprintCallable, Category="MobFort|Material")
	static bool SetGradientRow(UMaterialInstanceDynamic* Instance, EMobFortGradientRow Row, float Index);

	/** @return Whether a material is one of MobFort's, which is whether it reflects a panorama at all. */
	UFUNCTION(BlueprintPure, Category="MobFort|Material")
	static bool IsFortMaterial(UMaterialInstanceDynamic* Instance);

protected:
	/** The parameter behind a row. */
	static FName GetGradientRowParameter(EMobFortGradientRow Row);

	/** Writes a texture parameter only when the material declares it. */
	static bool SetTextureIfPresent(UMaterialInstanceDynamic* Instance, FName Parameter, UTexture* Value);

	/** Writes a scalar parameter only when the material declares it. */
	static bool SetScalarIfPresent(UMaterialInstanceDynamic* Instance, FName Parameter, float Value);
};
