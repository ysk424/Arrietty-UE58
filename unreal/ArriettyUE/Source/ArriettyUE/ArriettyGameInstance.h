#pragma once
#include "CoreMinimal.h"
#include "Engine/GameInstance.h"
#include "ArriettyGameInstance.generated.h"

UCLASS()
class ARRIETTYUE_API UArriettyGameInstance : public UGameInstance
{
    GENERATED_BODY()
public:
    virtual void Init() override;
};
