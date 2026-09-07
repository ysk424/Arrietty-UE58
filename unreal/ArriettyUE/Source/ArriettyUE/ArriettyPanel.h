#pragma once
#include "CoreMinimal.h"
#include "Blueprint/UserWidget.h"
#include "ArriettyPanel.generated.h"

UCLASS()
class ARRIETTYUE_API UArriettyPanel : public UUserWidget
{
    GENERATED_BODY()
public:
    TSharedPtr<FJsonObject> Telemetry;
    FString Status = TEXT("P: START   ESC: SETUP");
    bool bPlaying = false;
protected:
    virtual int32 NativePaint(const FPaintArgs& Args, const FGeometry& Geometry,
        const FSlateRect& Culling, FSlateWindowElementList& Elements, int32 Layer,
        const FWidgetStyle& Style, bool ParentEnabled) const override;
};
