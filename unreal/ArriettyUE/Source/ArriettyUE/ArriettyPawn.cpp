#include "ArriettyPawn.h"
#include "ArriettyPanel.h"
#include "ArriettySetup.h"
#include "Camera/CameraComponent.h"
#include "Components/WidgetComponent.h"
#include "HeadMountedDisplayFunctionLibrary.h"
#include "Engine/Engine.h"
#include "IXRTrackingSystem.h"
#include "IXRCamera.h"
#include "Common/UdpSocketBuilder.h"
#include "SocketSubsystem.h"
#include "Sockets.h"
#include "Dom/JsonObject.h"
#include "Serialization/JsonReader.h"
#include "Serialization/JsonSerializer.h"
#include "Misc/FileHelper.h"
#include "Misc/Paths.h"
#include "Kismet/KismetSystemLibrary.h"
#include "GameFramework/PlayerController.h"
#include "Engine/World.h"
#include "UnrealClient.h"
#include "Engine/DirectionalLight.h"
#include "Components/DirectionalLightComponent.h"
#include "EngineUtils.h"

AArriettyPawn::AArriettyPawn()
{
    PrimaryActorTick.bCanEverTick=true;
    AutoPossessPlayer=EAutoReceiveInput::Player0;
    Origin=CreateDefaultSubobject<USceneComponent>(TEXT("Vehicle")); SetRootComponent(Origin);
    Tracking=CreateDefaultSubobject<USceneComponent>(TEXT("XROrigin")); Tracking->SetupAttachment(Origin);
    Camera=CreateDefaultSubobject<UCameraComponent>(TEXT("HMD")); Camera->SetupAttachment(Tracking);
    Camera->bLockToHmd=true; Camera->bUsePawnControlRotation=false; Camera->SetFieldOfView(95);
    PanelComponent=CreateDefaultSubobject<UWidgetComponent>(TEXT("Instruments"));
    PanelComponent->SetupAttachment(Origin);
    PanelComponent->SetWidgetSpace(EWidgetSpace::World);
    PanelComponent->SetWidgetClass(UArriettyPanel::StaticClass());
    PanelComponent->SetDrawSize(FVector2D(1500,540));
    PanelComponent->SetRelativeLocation(FVector(130,0,100));
    PanelComponent->SetRelativeRotation(FRotator(24.78,180,0));
    PanelComponent->SetRelativeScale3D(FVector(.085));
    PanelComponent->SetTwoSided(true);
    PanelComponent->SetCollisionEnabled(ECollisionEnabled::NoCollision);
    PanelComponent->SetRedrawTime(1.f/30);
}

void AArriettyPawn::BeginPlay()
{
    Super::BeginPlay();
    BeganAt=FPlatformTime::Seconds();
    PanelComponent->InitWidget(); Panel=Cast<UArriettyPanel>(PanelComponent->GetWidget());
    if(auto Material=LoadObject<UMaterialInterface>(nullptr,TEXT("/Game/Materials/M_Instruments.M_Instruments")))
        PanelComponent->SetMaterial(0,Material);
    FString Session=FPlatformMisc::GetEnvironmentVariable(TEXT("ARRIETTY_UE_SESSION"));
    FString Data;
    TSharedPtr<FJsonObject> Config;
    if(!FFileHelper::LoadFileToString(Data,*Session) || !FJsonSerializer::Deserialize(TJsonReaderFactory<>::Create(Data),Config) || !Config.IsValid())
    {
        if(Panel) Panel->Status=TEXT("Launch with start-ue.ps1");
        UE_LOG(LogTemp,Error,TEXT("ARRIETTY_UE_SESSION_MISSING")); return;
    }
    Token=Config->GetStringField(TEXT("token"));
    bOffline=!Config->GetBoolField(TEXT("hardware"));
    bSmoke=FParse::Param(FCommandLine::Get(),TEXT("ArriettySmoke"));
    Remote=ISocketSubsystem::Get(PLATFORM_SOCKETSUBSYSTEM)->CreateInternetAddr();
    bool Valid; Remote->SetIp(TEXT("127.0.0.1"),Valid); Remote->SetPort(Config->GetIntegerField(TEXT("port")));
    Socket=FUdpSocketBuilder(TEXT("ArriettyLoopback")).AsNonBlocking().BoundToAddress(FIPv4Address::InternalLoopback).BoundToPort(0).WithReceiveBufferSize(65536);
    if(bOffline) { Camera->bLockToHmd=false; Camera->SetRelativeLocation(FVector(0,0,160)); Camera->SetRelativeRotation(FRotator(-15,0,0)); }
    else UHeadMountedDisplayFunctionLibrary::SetTrackingOrigin(EHMDTrackingOrigin::LocalFloor);
    FString WorldData;
    TSharedPtr<FJsonObject> World;
    if(FFileHelper::LoadFileToString(WorldData,*(FPaths::ProjectContentDir()/TEXT("SecretWorld/world.json"))) &&
       FJsonSerializer::Deserialize(TJsonReaderFactory<>::Create(WorldData),World))
        SetActorRotation(FRotator(0,180-World->GetNumberField(TEXT("initial_heading_degrees")),0));
    if(Panel) Panel->Status=bOffline?TEXT("OFFLINE | P: START"):TEXT("READY | P: START");
    FString SolarData;
    TSharedPtr<FJsonObject> Solar;
    if(FFileHelper::LoadFileToString(SolarData,*FPlatformMisc::GetEnvironmentVariable(TEXT("ARRIETTY_UE_SOLAR"))) &&
       FJsonSerializer::Deserialize(TJsonReaderFactory<>::Create(SolarData),Solar))
    {
        const FString Local=Solar->GetStringField(TEXT("local_time")); SetupDate=Local.Left(10); SetupTime=Local.Mid(11,5);
        FString Mode;
        bAuthoredLighting=Solar->TryGetStringField(TEXT("solar_mode"),Mode) && Mode==TEXT("authored");
        if(bAuthoredLighting)
        {
            SetupWorldName=Solar->GetStringField(TEXT("output_name"));
            SetupMessage=TEXT("Lighting and atmosphere from the exported world.");
            const auto& Start=Solar->GetArrayField(TEXT("spawn_location_cm"));
            SetActorLocationAndRotation(FVector(Start[0]->AsNumber(),Start[1]->AsNumber(),Start[2]->AsNumber()),
                FRotator(0,180-Solar->GetNumberField(TEXT("initial_heading_degrees")),0));
            const FString ActualMap=GetWorld()->GetPackage()->GetName();
            if(ActualMap!=Solar->GetStringField(TEXT("map")))
            { UE_LOG(LogTemp,Error,TEXT("ARRIETTY_WORLD_WRONG_MAP")); FPlatformMisc::RequestExitWithStatus(true,1); return; }
            UE_LOG(LogTemp,Display,TEXT("ARRIETTY_WORLD_MAP_READY %s"),*ActualMap);
        }
    }
    if(auto PC=Cast<APlayerController>(GetController()); PC && !bSmoke)
    {
        Setup=CreateWidget<UArriettySetup>(PC); Setup->Pawn=this;
        Setup->AddToViewport(); Setup->SetDesiredSizeInViewport(FVector2D(430,460)); Setup->SetPositionInViewport(FVector2D(30,30));
    }
    UE_LOG(LogTemp,Display,TEXT("ARRIETTY_UE_PAWN_READY offline=%d"),bOffline);
}

void AArriettyPawn::Send(bool Quit)
{
    if(!Socket) return;
    TSharedRef<FJsonObject> P=MakeShared<FJsonObject>();
    P->SetNumberField(TEXT("protocol"),1); P->SetStringField(TEXT("token"),Token);
    P->SetNumberField(TEXT("seq"),++Sequence); P->SetBoolField(TEXT("play"),bPlaying);
    P->SetBoolField(TEXT("quit"),Quit); P->SetNumberField(TEXT("aligned"),Aligned);
    P->SetNumberField(TEXT("recenter_id"),RecenterId);
    P->SetNumberField(TEXT("alignment_bearing"),AlignmentBearing);
    const bool Tracked=bOffline || (GEngine->XRSystem.IsValid() && GEngine->XRSystem->IsTracking(IXRTrackingSystem::HMDDeviceId));
    P->SetBoolField(TEXT("hmd_valid"),Tracked);
    P->SetNumberField(TEXT("apply_id"),ApplyId);
    P->SetStringField(TEXT("local_date"),SetupDate); P->SetStringField(TEXT("local_time"),SetupTime);
    if(bOffline)
    {
        auto PC=Cast<APlayerController>(GetController());
        int32 Buttons=0;
        if(PC) for(int32 I=0;I<8;++I)
        {
            const FKey Keys[]={EKeys::One,EKeys::Two,EKeys::Three,EKeys::Four,EKeys::Five,EKeys::Six,EKeys::Seven,EKeys::Eight};
            if(PC->IsInputKeyDown(Keys[I])) Buttons|=1<<I;
        }
        const double Age=FPlatformTime::Seconds()-BeganAt;
        if(bSmoke) { Buttons=(Age>2 && Age<2.2)?1:((Age>3 && Age<3.2)?2:((Age>4 && Age<4.2)?12:0)); OfflineSpeed=27; }
        P->SetNumberField(TEXT("buttons"),Buttons);
        P->SetNumberField(TEXT("speed"),OfflineSpeed);
        P->SetNumberField(TEXT("power"),OfflineSpeed>0?250:0);
        const double Steer=PC?(PC->IsInputKeyDown(EKeys::Right)?-8:(PC->IsInputKeyDown(EKeys::Left)?8:0)):0;
        P->SetNumberField(TEXT("steer"),Steer);
    }
    FString Json; FJsonSerializer::Serialize(P,TJsonWriterFactory<>::Create(&Json));
    FTCHARToUTF8 Bytes(*Json); int32 Sent; Socket->SendTo(reinterpret_cast<const uint8*>(Bytes.Get()),Bytes.Length(),Sent,*Remote);
}

void AArriettyPawn::Tick(float Delta)
{
    Super::Tick(Delta);
    auto PC=Cast<APlayerController>(GetController());
    if(PC)
    {
        if(PC->WasInputKeyJustPressed(EKeys::P)) StartSimulation();
        if(PC->WasInputKeyJustPressed(EKeys::Escape)) { bPlaying=false; Aligned=0; PendingAlignment=0; }
        if(bPlaying && PC->WasInputKeyJustPressed(EKeys::R))
        {
            ++RecenterId; Aligned=0; PendingAlignment=0;
        }
        if(bOffline) OfflineSpeed=FMath::Clamp(OfflineSpeed+(PC->IsInputKeyDown(EKeys::Up)?8.f:0.f)*Delta-(PC->IsInputKeyDown(EKeys::Down)?8.f:0.f)*Delta,0.f,60.f);
    }
    const double Now=FPlatformTime::Seconds();
    if(Setup)
    {
        Setup->SetVisibility(bPlaying?ESlateVisibility::Collapsed:ESlateVisibility::Visible);
        if(PC)
        {
            PC->bShowMouseCursor=!bPlaying;
            if(bPlaying!=bInputWasPlaying)
            {
                bInputWasPlaying=bPlaying;
                if(bPlaying) PC->SetInputMode(FInputModeGameOnly());
                else PC->SetInputMode(FInputModeGameAndUI().SetHideCursorDuringCapture(false));
            }
        }
    }
    if(bSmoke && bOffline)
    {
        bPlaying=Now-BeganAt>1 && Now-BeganAt<9;
        if(Now-BeganAt>6 && !bCaptured)
        {
            bCaptured=true;
            FScreenshotRequest::RequestScreenshot(FPaths::ProjectSavedDir()/TEXT("Screenshots/ue-offline.png"),false,false);
            UE_LOG(LogTemp,Display,TEXT("ARRIETTY_UE_SMOKE_POSE %s"),*GetActorLocation().ToString());
        }
        if(Now-BeganAt>11)
        {
            if(ReceivedSequence>20 && bSmokeMoved && bSmokeAirborne)
            { UE_LOG(LogTemp,Display,TEXT("ARRIETTY_UE_SMOKE_DONE packets=%d moved=1 airborne=1"),ReceivedSequence); }
            else { UE_LOG(LogTemp,Error,TEXT("ARRIETTY_UE_SMOKE_FAILED packets=%d moved=%d airborne=%d"),ReceivedSequence,bSmokeMoved,bSmokeAirborne); }
            UKismetSystemLibrary::QuitGame(this,PC,EQuitPreference::Quit,false);
        }
    }
    Send();
    if(!Socket) return;
    uint32 Available; int32 Iterations=0;
    while(Socket->HasPendingData(Available) && ++Iterations<=64)
    {
        TArray<uint8> Bytes; Bytes.SetNumUninitialized(FMath::Min(Available,65535u)+1);
        auto Sender=ISocketSubsystem::Get(PLATFORM_SOCKETSUBSYSTEM)->CreateInternetAddr();
        int32 Read=0;
        if(!Socket->RecvFrom(Bytes.GetData(),Bytes.Num()-1,Read,*Sender)) break;
        if(Sender->ToString(true)!=Remote->ToString(true)) continue;
        Bytes[Read]=0;
        TSharedPtr<FJsonObject> P;
        if(!FJsonSerializer::Deserialize(TJsonReaderFactory<>::Create(UTF8_TO_TCHAR(reinterpret_cast<char*>(Bytes.GetData()))),P) || !P.IsValid()) continue;
        FString ResponseToken; double ResponseSeq=0;
        if(!P->TryGetStringField(TEXT("token"),ResponseToken) || ResponseToken!=Token || !P->TryGetNumberField(TEXT("seq"),ResponseSeq) || ResponseSeq<=ReceivedSequence) continue;
        ReceivedSequence=ResponseSeq; LastPacket=Now;
        bool Playing=false; P->TryGetBoolField(TEXT("playing"),Playing);
        if(Panel) { Panel->Telemetry=P; Panel->bPlaying=Playing; Panel->Status=bOffline?TEXT("OFFLINE | R: ALIGN | ESC: SETUP"):TEXT("LIVE | R: ALIGN | ESC: SETUP"); }
        if(!Playing)
        {
            double Ack=0;
            if(P->TryGetNumberField(TEXT("apply_id"),Ack) && int32(Ack)!=AppliedId)
            {
                AppliedId=Ack;
                const FString Error=P->GetStringField(TEXT("apply_error"));
                if(Error.IsEmpty())
                {
                    if(AppliedId==ApplyId) bSetupDirty=false;
                    SetupMessage=TEXT("Applied: ")+P->GetStringField(TEXT("local_time"));
                    const double Azimuth=P->GetNumberField(TEXT("sun_azimuth")),Elevation=P->GetNumberField(TEXT("sun_elevation"));
                    for(TActorIterator<ADirectionalLight> It(GetWorld());!bAuthoredLighting && It;++It)
                    {
                        It->SetActorRotation(FRotator(-Elevation,Azimuth+180,0));
                        Cast<UDirectionalLightComponent>(It->GetLightComponent())->SetIntensity(50000*FMath::Clamp((Elevation+.3)/8.,0.,1.));
                    }
                }
                else SetupMessage=Error;
            }
        }
        const TArray<TSharedPtr<FJsonValue>>* Pose;
        if(bPlaying && Playing && P->TryGetArrayField(TEXT("pose"),Pose) && Pose->Num()==6)
        {
            FVector Position((*Pose)[0]->AsNumber(),(*Pose)[1]->AsNumber(),(*Pose)[2]->AsNumber());
            bSmokeMoved|=Position.Size2D()>100;
            bool Airborne=false; P->TryGetBoolField(TEXT("airborne"),Airborne); bSmokeAirborne|=Airborne;
            FRotator Rotation((*Pose)[3]->AsNumber(),(*Pose)[4]->AsNumber(),(*Pose)[5]->AsNumber());
            double AppliedAlignment=0; P->TryGetNumberField(TEXT("alignment_applied"),AppliedAlignment);
            // An in-flight reply from before calibration must not rotate the
            // camera back to the old runway heading while its ack is pending.
            if(CanApplyPose(int32(AppliedAlignment)) && !Position.ContainsNaN() && !Rotation.ContainsNaN())
                SetActorLocationAndRotation(Position,Rotation);
            const int32 Request=P->GetIntegerField(TEXT("align_request"));
            double RecenterAck=0; P->TryGetNumberField(TEXT("recenter_id"),RecenterAck);
            if(Request>0 && Request!=Aligned && int32(RecenterAck)==RecenterId)
            {
                if(bOffline) { AlignmentBearing=Rotation.Yaw; Aligned=Request; }
                else PendingAlignment=Request;
                if(Panel && !bOffline) Panel->Status=TEXT("ALIGNING | FACE BICYCLE FORWARD");
            }
        }
    }
    if(LastPacket>0 && Now-LastPacket>1)
    {
        bPlaying=false; Aligned=0; PendingAlignment=0;
        if(Panel) { Panel->Status=TEXT("CONNECTION LOST | P: RESTART"); Panel->bPlaying=false; }
    }
}

void AArriettyPawn::CalcCamera(float DeltaTime, FMinimalViewInfo& OutResult)
{
    // Capture the view the rider is already looking at. Its XY projection is
    // the bicycle's new forward, not a correction back to the runway bearing.
    FQuat HmdOrientation=FQuat::Identity;
    FVector HmdPosition=FVector::ZeroVector;
    auto XR=GEngine?GEngine->XRSystem:nullptr;
    const bool Tracked=!bOffline && XR.IsValid() && XR->GetXRCamera().IsValid() && XR->IsHeadTrackingAllowedForWorld(*GetWorld()) &&
        XR->IsTracking(IXRTrackingSystem::HMDDeviceId) &&
        XR->GetCurrentPose(IXRTrackingSystem::HMDDeviceId,HmdOrientation,HmdPosition) &&
        !HmdOrientation.ContainsNaN() && HmdOrientation.SizeSquared()>UE_SMALL_NUMBER && !HmdPosition.ContainsNaN();
    bool Applied=false;
    double RawYaw=0;
    Camera->GetCameraView(DeltaTime,OutResult);
    if(Tracked)
    {
        HmdOrientation.Normalize();
        const FVector Forward=HmdOrientation.GetForwardVector();
        RawYaw=FMath::RadiansToDegrees(FMath::Atan2(Forward.Y,Forward.X));
        const FVector ViewForward=OutResult.Rotation.Vector();
        if(bPlaying && PendingAlignment>0 && ViewForward.SizeSquared2D()>1.e-4)
        {
            AlignmentBearing=FMath::RadiansToDegrees(FMath::Atan2(ViewForward.Y,ViewForward.X));
            const FQuat TrackingWorldRotation=Tracking->GetComponentQuat();
            FRotator BikeRotation=GetActorRotation(); BikeRotation.Yaw=AlignmentBearing;
            SetActorRotation(BikeRotation);
            // Re-express the same tracking-to-world rotation under the new
            // vehicle yaw. This preserves the view, including head pitch/roll.
            const FQuat TrackingRotation=GetActorQuat().Inverse()*TrackingWorldRotation;
            Tracking->SetRelativeRotation(TrackingRotation);
            const FVector Offset=TrackingRotation.RotateVector(HmdPosition);
            Tracking->SetRelativeLocation(FVector(-Offset.X,-Offset.Y,0));
            Camera->GetCameraView(DeltaTime,OutResult);
            Applied=true;
        }
    }
    const double Residual=FRotator::NormalizeAxis(OutResult.Rotation.Yaw-GetActorRotation().Yaw);
    if(Applied && FMath::Abs(Residual)<1.0)
    {
        Aligned=PendingAlignment; PendingAlignment=0;
        UE_LOG(LogTemp,Display,TEXT("ARRIETTY_UE_HMD_ALIGNED id=%d raw_yaw=%.2f origin_yaw=%.2f bike_yaw=%.2f view_yaw=%.2f residual=%.3f"),
            Aligned,RawYaw,Tracking->GetRelativeRotation().Yaw,GetActorRotation().Yaw,OutResult.Rotation.Yaw,Residual);
    }
    const double Now=FPlatformTime::Seconds();
    if(bPlaying && Now-LastViewLog>=1)
    {
        LastViewLog=Now;
        UE_LOG(LogTemp,Display,TEXT("ARRIETTY_UE_VIEW aligned=%d pending=%d tracked=%d bike_yaw=%.2f view_yaw=%.2f raw_yaw=%.2f origin_yaw=%.2f relative_yaw=%.2f north_cm=%.1f east_cm=%.1f"),
            Aligned,PendingAlignment,Tracked,GetActorRotation().Yaw,OutResult.Rotation.Yaw,RawYaw,Tracking->GetRelativeRotation().Yaw,Residual,GetActorLocation().X,GetActorLocation().Y);
    }
}

void AArriettyPawn::EndPlay(const EEndPlayReason::Type Reason)
{
    bPlaying=false; for(int I=0;I<3;++I) Send(true);
    if(Socket) { Socket->Close(); ISocketSubsystem::Get(PLATFORM_SOCKETSUBSYSTEM)->DestroySocket(Socket); Socket=nullptr; }
    Super::EndPlay(Reason);
}
