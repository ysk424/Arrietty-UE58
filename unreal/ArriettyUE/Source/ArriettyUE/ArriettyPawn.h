#pragma once
#include "CoreMinimal.h"
#include "GameFramework/Pawn.h"
#include "ArriettyPawn.generated.h"
class UCameraComponent;
class UWidgetComponent;
class UArriettyPanel;
class FSocket;
class FInternetAddr;

UCLASS()
class ARRIETTYUE_API AArriettyPawn : public APawn
{
    GENERATED_BODY()
public:
    AArriettyPawn();
    virtual void BeginPlay() override;
    virtual void Tick(float Delta) override;
    virtual void CalcCamera(float DeltaTime, FMinimalViewInfo& OutResult) override;
    virtual void EndPlay(const EEndPlayReason::Type Reason) override;
    FString SetupDate, SetupTime, SetupMessage=TEXT("Local time stays fixed during play.");
    bool bSetupDirty=false;
    int32 ApplyId=0;
    void StartSimulation() { if(!bSetupDirty) bPlaying=true; }
private:
    friend class FArriettyHmdAlignmentTest;
    UPROPERTY() TObjectPtr<USceneComponent> Origin;
    UPROPERTY() TObjectPtr<USceneComponent> Tracking;
    UPROPERTY() TObjectPtr<UCameraComponent> Camera;
    UPROPERTY() TObjectPtr<UWidgetComponent> PanelComponent;
    UPROPERTY() TObjectPtr<UArriettyPanel> Panel;
    UPROPERTY() TObjectPtr<class UArriettySetup> Setup;
    FSocket* Socket = nullptr;
    TSharedPtr<FInternetAddr> Remote;
    FString Token;
    bool bPlaying=false, bOffline=true, bSmoke=false, bCaptured=false, bSmokeMoved=false, bSmokeAirborne=false;
    int32 Sequence=0, Aligned=0, PendingAlignment=0, RecenterId=0, ReceivedSequence=-1;
    float OfflineSpeed=0;
    double LastPacket=0, BeganAt=0, LastViewLog=0;
    int32 AppliedId=-1;
    bool bInputWasPlaying=true;
    void Send(bool Quit=false);
};
