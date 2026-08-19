// Copyright (c) Jared Taylor

#include "MobFortWetnessComponent.h"

#include "MobFortTypes.h"
#include "Components/MeshComponent.h"
#include "GameFramework/Actor.h"

UMobFortWetnessComponent::UMobFortWetnessComponent()
{
	PrimaryComponentTick.bCanEverTick = true;
	PrimaryComponentTick.bStartWithTickEnabled = true;
}

void UMobFortWetnessComponent::BeginPlay()
{
	Super::BeginPlay();

	RefreshMeshes();
}

void UMobFortWetnessComponent::RefreshMeshes()
{
	Meshes.Reset();

	const AActor* Owner = GetOwner();
	if (!Owner)
	{
		return;
	}

	TInlineComponentArray<UMeshComponent*> Found(Owner);
	for (UMeshComponent* Mesh : Found)
	{
		if (MeshTags.IsEmpty() || MeshTags.ContainsByPredicate(
			[Mesh](const FName& Tag) { return Mesh->ComponentHasTag(Tag); }))
		{
			Meshes.Add(Mesh);
		}
	}

	// Whatever the last write left on a mesh that is no longer here means nothing, and a mesh that
	// has just arrived has never been written at all.
	WrittenLineOffset = MAX_flt;
	WrittenWetness = MAX_flt;
}

bool UMobFortWetnessComponent::SampleWaterline_Implementation(float& OutWorldZ) const
{
	OutWorldZ = 0.f;
	return false;
}

bool UMobFortWetnessComponent::GetVerticalExtent(float& OutBottom, float& OutTop) const
{
	const AActor* Owner = GetOwner();
	if (!Owner || Meshes.IsEmpty())
	{
		return false;
	}

	const float OriginZ = Owner->GetActorLocation().Z;
	float Bottom = MAX_flt;
	float Top = -MAX_flt;

	for (const UMeshComponent* Mesh : Meshes)
	{
		if (!Mesh)
		{
			continue;
		}

		// The bounds the renderer already keeps, rather than CalcBounds: this runs every frame a
		// character is wet, and a skeletal mesh recomputing its own bounds from the bones is not
		// something to pay for twice.
		const FBoxSphereBounds& Bounds = Mesh->Bounds;
		Bottom = FMath::Min(Bottom, static_cast<float>(Bounds.Origin.Z - Bounds.BoxExtent.Z) - OriginZ);
		Top = FMath::Max(Top, static_cast<float>(Bounds.Origin.Z + Bounds.BoxExtent.Z) - OriginZ);
	}

	if (Top <= Bottom)
	{
		return false;
	}

	OutBottom = Bottom;
	OutTop = Top;
	return true;
}

float UMobFortWetnessComponent::GetWetLine() const
{
	float Bottom, Top;
	if (!GetVerticalExtent(Bottom, Top))
	{
		return 0.f;
	}
	return FMath::Clamp((LineOffset - Bottom) / (Top - Bottom), 0.f, 1.f);
}

void UMobFortWetnessComponent::SetWaterline(float WorldZ)
{
	const AActor* Owner = GetOwner();
	if (!Owner)
	{
		return;
	}

	float Bottom, Top;
	if (!GetVerticalExtent(Bottom, Top))
	{
		return;
	}

	// Clamped to the top: someone who swims under keeps a mark at the crown of their head and not
	// wherever the surface was, or the line has to fall back into range before drying shows at all.
	const float Offset = FMath::Clamp(WorldZ - Owner->GetActorLocation().Z, Bottom, Top);
	LineOffset = FMath::Max(LineOffset, Offset);
}

void UMobFortWetnessComponent::Soak(float Line01, float Amount)
{
	float Bottom, Top;
	if (!GetVerticalExtent(Bottom, Top))
	{
		return;
	}

	LineOffset = FMath::Max(LineOffset, FMath::Lerp(Bottom, Top, FMath::Clamp(Line01, 0.f, 1.f)));
	Wetness = FMath::Max(Wetness, FMath::Clamp(Amount, 0.f, 1.f));
	WriteMeshData();
}

void UMobFortWetnessComponent::Dry()
{
	float Bottom, Top;
	LineOffset = GetVerticalExtent(Bottom, Top) ? Bottom : 0.f;
	Wetness = 0.f;
	WriteMeshData();
}

void UMobFortWetnessComponent::TickComponent(float DeltaTime, ELevelTick TickType,
	FActorComponentTickFunction* ThisTickFunction)
{
	Super::TickComponent(DeltaTime, TickType, ThisTickFunction);

	float WaterZ;
	const bool bInWater = SampleWaterline(WaterZ);

	// A dry character out of water is the common case and it is the whole of the cost: one virtual
	// call, no bounds, no writes.
	if (!bInWater && Wetness <= 0.f)
	{
		return;
	}

	if (bInWater)
	{
		Wetness = SoakTime > 0.f ? FMath::Min(1.f, Wetness + DeltaTime / SoakTime) : 1.f;
		SetWaterline(WaterZ);
	}
	else
	{
		Wetness = FMath::Max(0.f, Wetness - DeltaTime / FMath::Max(DryTime, KINDA_SMALL_NUMBER));

		float Bottom, Top;
		if (GetVerticalExtent(Bottom, Top))
		{
			const float Fall = (Top - Bottom) / FMath::Max(DryTime * LineDryScale, KINDA_SMALL_NUMBER);
			LineOffset = FMath::Max(Bottom, LineOffset - Fall * DeltaTime);
		}
	}

	WriteMeshData();
}

void UMobFortWetnessComponent::WriteMeshData()
{
	const AActor* Owner = GetOwner();
	if (!Owner || Meshes.IsEmpty())
	{
		return;
	}

	if (FMath::IsNearlyEqual(LineOffset, WrittenLineOffset)
		&& FMath::IsNearlyEqual(Wetness, WrittenWetness))
	{
		return;
	}

	WrittenLineOffset = LineOffset;
	WrittenWetness = Wetness;

	const float WorldLineZ = Owner->GetActorLocation().Z + LineOffset;

	for (UMeshComponent* Mesh : Meshes)
	{
		if (!Mesh)
		{
			continue;
		}

		// The material measures the line against the object's local bounds, so each mesh is asked
		// for its own fraction: the same waterline is the waist of a body and the whole of a boot.
		const FBoxSphereBounds& Bounds = Mesh->Bounds;
		const float Height = FMath::Max(2.f * static_cast<float>(Bounds.BoxExtent.Z), KINDA_SMALL_NUMBER);
		const float BottomZ = static_cast<float>(Bounds.Origin.Z - Bounds.BoxExtent.Z);

		Mesh->SetCustomPrimitiveDataFloat(MobFortData::WetLine,
			FMath::Clamp((WorldLineZ - BottomZ) / Height, 0.f, 1.f));
		Mesh->SetCustomPrimitiveDataFloat(MobFortData::Wetness, Wetness);
	}
}
