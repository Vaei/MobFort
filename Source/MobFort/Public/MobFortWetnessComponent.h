// Copyright (c) Jared Taylor

#pragma once

#include "CoreMinimal.h"
#include "Components/ActorComponent.h"
#include "MobFortWetnessComponent.generated.h"

class UMeshComponent;

/**
 * How wet an actor is, and how far up it.
 *
 * A waterline and a strength, written to every mesh on the owner as custom primitive data. The
 * masters do the rest: darker, smoother and flatter below the line, and nothing at all above it.
 *
 * The line is a high water mark rather than where the water is now. Someone who wades out to the
 * bank is still wet to the waist, and drying is the line falling back down them - so the boots are
 * the last thing to dry, which is the only part of this anyone consciously notices.
 *
 * Where the water is comes from SampleWaterline, which does nothing here. MobFort has no idea what
 * a project's water is, and the whole feature is two floats, so a subclass that knows answers that
 * one question and inherits the rest.
 */
UCLASS(Blueprintable, ClassGroup=(Mob), meta=(BlueprintSpawnableComponent, DisplayName="Mob Fort Wetness"))
class MOBFORT_API UMobFortWetnessComponent : public UActorComponent
{
	GENERATED_BODY()

public:
	UMobFortWetnessComponent();

	//~ Begin UActorComponent Interface
	virtual void BeginPlay() override;
	virtual void TickComponent(float DeltaTime, ELevelTick TickType, FActorComponentTickFunction* ThisTickFunction) override;
	//~ End UActorComponent Interface

	/** How long a soaked surface takes to dry out completely. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category="Wetness", meta=(ClampMin="0.01", ForceUnits="s"))
	float DryTime = 20.f;

	/**
	 * How long in the water it takes to soak through.
	 *
	 * Short, but not zero: a character who steps into a puddle and turns black in one frame reads as
	 * a material swap rather than as water.
	 */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category="Wetness", meta=(ClampMin="0.0", ForceUnits="s"))
	float SoakTime = 0.6f;

	/**
	 * How much sooner the line falls than the wetness fades, as a fraction of DryTime.
	 *
	 * Below 1 the line lands on the feet while there is still water left in them, which is what
	 * makes drying read as draining downwards rather than as a fade.
	 */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category="Wetness", meta=(ClampMin="0.05", ClampMax="1.0"))
	float LineDryScale = 0.6f;

	/**
	 * Which meshes are written. Empty writes every mesh on the owner.
	 *
	 * Anything whose material has no wetness switched on ignores what it is given, so the cost of
	 * writing one is a render state update and nothing else.
	 */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category="Wetness")
	TArray<FName> MeshTags;

	/** How far up the owner the water reached, 0 dry and 1 over their head. */
	UFUNCTION(BlueprintPure, Category="Wetness")
	float GetWetLine() const;

	/** How wet the surface below the line is. */
	UFUNCTION(BlueprintPure, Category="Wetness")
	float GetWetness() const { return Wetness; }

	/**
	 * Marks the owner wet up to a world height, which is what a tick in water does.
	 *
	 * Never lowers the line: that is what makes it a high water mark. Call it every frame the owner
	 * is in water, or override SampleWaterline and let the component call it.
	 */
	UFUNCTION(BlueprintCallable, Category="Wetness")
	void SetWaterline(float WorldZ);

	/** Soaks the owner to a fraction of their own height, for anything that is not a body of water. */
	UFUNCTION(BlueprintCallable, Category="Wetness")
	void Soak(float Line01, float Amount = 1.f);

	/** Dry immediately, with no fade. For a teleport, a respawn or a possession. */
	UFUNCTION(BlueprintCallable, Category="Wetness")
	void Dry();

	/** Finds the meshes to write again. Call after adding or swapping one at run time. */
	UFUNCTION(BlueprintCallable, Category="Wetness")
	void RefreshMeshes();

protected:
	/**
	 * Where the water surface is on the owner this frame, in world Z. False when it is in none.
	 *
	 * Does nothing by default. MobFort cannot know what a project's water is, and guessing would be
	 * worse than saying nothing, so this is the one thing a project supplies.
	 */
	UFUNCTION(BlueprintNativeEvent, Category="Wetness")
	bool SampleWaterline(float& OutWorldZ) const;
	virtual bool SampleWaterline_Implementation(float& OutWorldZ) const;

	/** Writes the current state to every target mesh. */
	void WriteMeshData();

	/** The owner's extent in world Z, relative to its own origin. False when there is nothing to measure. */
	bool GetVerticalExtent(float& OutBottom, float& OutTop) const;

	UPROPERTY(Transient)
	TArray<TObjectPtr<UMeshComponent>> Meshes;

	/**
	 * The waterline in world Z, relative to the owner's origin.
	 *
	 * An offset rather than a fraction because the meshes it is written to do not share a height - a
	 * blade held overhead and the body it belongs to are the same line at two different fractions.
	 *
	 * Starts below anything the owner could be, so the first waterline sets it outright. Zero would
	 * be the owner's own origin, and a first step into a puddle would read as waist deep.
	 */
	float LineOffset = -MAX_flt;

	float Wetness = 0.f;

	/** What was last written, so a character standing still costs no render state updates. */
	float WrittenLineOffset = MAX_flt;
	float WrittenWetness = MAX_flt;
};
