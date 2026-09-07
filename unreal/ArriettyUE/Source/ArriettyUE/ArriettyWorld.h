#pragma once
#include "CoreMinimal.h"
#include "GameFramework/Actor.h"
#include "ArriettyWorld.generated.h"

UCLASS()
class ARRIETTYUE_API AArriettyWorld : public AActor
{
    GENERATED_BODY()
public:
    AArriettyWorld();
    virtual void BeginPlay() override;
    UFUNCTION(CallInEditor, BlueprintCallable, Category="Secret World") bool LoadWorld();
private:
    UPROPERTY() TArray<TObjectPtr<class UProceduralMeshComponent>> Meshes;
    UPROPERTY() TObjectPtr<class UTexture2D> Reef;
};
