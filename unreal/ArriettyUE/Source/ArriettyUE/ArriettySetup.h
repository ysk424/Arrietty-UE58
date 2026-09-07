#pragma once
#include "CoreMinimal.h"
#include "Blueprint/UserWidget.h"
#include "ArriettySetup.generated.h"
class AArriettyPawn;
UCLASS()
class ARRIETTYUE_API UArriettySetup : public UUserWidget
{
    GENERATED_BODY()
public:
    UPROPERTY() TObjectPtr<AArriettyPawn> Pawn;
protected:
    virtual TSharedRef<SWidget> RebuildWidget() override;
};
