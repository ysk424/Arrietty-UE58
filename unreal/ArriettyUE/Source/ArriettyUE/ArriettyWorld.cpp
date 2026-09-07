#include "ArriettyWorld.h"
#include "ProceduralMeshComponent.h"
#include "Engine/Texture2D.h"
#include "Materials/MaterialInstanceDynamic.h"
#include "Misc/FileHelper.h"
#include "Misc/Paths.h"
#include "Serialization/MemoryReader.h"
#include "Serialization/JsonSerializer.h"
#include "Engine/DirectionalLight.h"
#include "Components/DirectionalLightComponent.h"
#include "Engine/SkyLight.h"
#include "Components/SkyLightComponent.h"
#include "Components/SkyAtmosphereComponent.h"
#include "EngineUtils.h"
#include "Engine/World.h"

AArriettyWorld::AArriettyWorld()
{
    RootComponent=CreateDefaultSubobject<USceneComponent>(TEXT("SecretWorld"));
}
void AArriettyWorld::BeginPlay() { Super::BeginPlay(); if(Meshes.IsEmpty()) LoadWorld(); }

bool AArriettyWorld::LoadWorld()
{
    const FString Dir=FPaths::ProjectContentDir()/TEXT("SecretWorld");
    FString Data;
    TSharedPtr<FJsonObject> Meta;
    TArray<uint8> Binary;
    if(!FFileHelper::LoadFileToString(Data,*(Dir/TEXT("world.json"))) ||
       !FJsonSerializer::Deserialize(TJsonReaderFactory<>::Create(Data),Meta) || !Meta.IsValid() ||
       !FFileHelper::LoadFileToArray(Binary,*(Dir/TEXT("world.bin"))))
    { UE_LOG(LogTemp,Error,TEXT("ARRIETTY_UE_WORLD_MISSING run tools/prepare_ue.ps1")); return false; }
    if(Binary.Num()<12 || FMemory::Memcmp(Binary.GetData(),"ARRW0001",8)!=0) return false;
    auto Base=LoadObject<UMaterialInterface>(nullptr,TEXT("/Game/Materials/M_World.M_World"));
    auto Water=LoadObject<UMaterialInterface>(nullptr,TEXT("/Game/Materials/M_Water.M_Water"));
    if(!Base || !Water) { UE_LOG(LogTemp,Error,TEXT("ARRIETTY_UE_MATERIALS_MISSING")); return false; }
    for(auto M:Meshes) if(M) M->DestroyComponent(); Meshes.Empty();
    TArray<uint8> Pixels;
    const int32 Width=Meta->GetIntegerField(TEXT("water_width")),Height=Meta->GetIntegerField(TEXT("water_height"));
    if(Width<1 || Height<1 || Width>4096 || Height>4096 ||
       !FFileHelper::LoadFileToArray(Pixels,*(Dir/TEXT("reef.bgra"))) || Pixels.Num()!=Width*Height*4) return false;
    Reef=UTexture2D::CreateTransient(Width,Height,PF_B8G8R8A8);
    Reef->SRGB=false; Reef->NeverStream=true;
    Reef->AddressX=TA_Clamp; Reef->AddressY=TA_Clamp;
    auto& Mip=Reef->GetPlatformData()->Mips[0];
    void* Dest=Mip.BulkData.Lock(LOCK_READ_WRITE); FMemory::Memcpy(Dest,Pixels.GetData(),Pixels.Num()); Mip.BulkData.Unlock(); Reef->UpdateResource();
    FMemoryReader Reader(Binary,true); Reader.Seek(8);
    uint32 Count=0; Reader<<Count;
    if(Count>10000) return false;
    int64 Total=0; int32 CollisionSections=0;
    for(uint32 Section=0;Section<Count;++Section)
    {
        if(Reader.TotalSize()-Reader.Tell()<24) return false;
        uint32 N=0,Flags=0; float R,G,B,Rough;
        Reader<<N<<Flags<<R<<G<<B<<Rough;
        if(N>6000000 || N%3 || Reader.TotalSize()-Reader.Tell()<int64(N)*32) return false;
        TArray<FVector> V,Normals; TArray<FVector2D> UV; TArray<int32> Indices;
        V.Reserve(N); Normals.Reserve(N); UV.Reserve(N); Indices.Reserve(N);
        for(uint32 I=0;I<N;++I)
        {
            float X,Y,Z,NX,NY,NZ,U,W; Reader<<X<<Y<<Z<<NX<<NY<<NZ<<U<<W;
            V.Add(FVector(X,Y,Z)); Normals.Add(FVector(NX,NY,NZ)); UV.Add(FVector2D(U,W)); Indices.Add(I);
        }
        auto Mesh=NewObject<UProceduralMeshComponent>(this);
        Mesh->SetupAttachment(RootComponent); Mesh->RegisterComponent();
        Mesh->bUseAsyncCooking=true; Mesh->bUseComplexAsSimpleCollision=true;
        const bool Collision=(Flags&1)!=0;
        Mesh->SetCollisionEnabled(Collision?ECollisionEnabled::QueryOnly:ECollisionEnabled::NoCollision);
        Mesh->SetCollisionResponseToAllChannels(ECR_Block);
        Mesh->SetCastShadow(Collision);
        Mesh->CreateMeshSection_LinearColor(0,V,Indices,Normals,UV,TArray<FLinearColor>(),TArray<FProcMeshTangent>(),Collision);
        auto Material=UMaterialInstanceDynamic::Create((Flags&2)?Water:Base,this);
        Material->SetVectorParameterValue(TEXT("Tint"),FLinearColor(R,G,B,1));
        Material->SetScalarParameterValue(TEXT("Roughness"),Rough);
        if(Flags&2) Material->SetTextureParameterValue(TEXT("Reef"),Reef);
        Mesh->SetMaterial(0,Material); Meshes.Add(Mesh); Total+=N/3; CollisionSections+=Collision;
    }
    if(Reader.IsError() || Reader.Tell()!=Reader.TotalSize()) return false;
    double Azimuth=Meta->GetNumberField(TEXT("sun_azimuth")),Elevation=Meta->GetNumberField(TEXT("sun_elevation"));
    const FString SolarPath=FPlatformMisc::GetEnvironmentVariable(TEXT("ARRIETTY_UE_SOLAR"));
    TSharedPtr<FJsonObject> Solar;
    if(!SolarPath.IsEmpty() && FFileHelper::LoadFileToString(Data,*SolarPath) &&
       FJsonSerializer::Deserialize(TJsonReaderFactory<>::Create(Data),Solar))
    { Azimuth=Solar->GetNumberField(TEXT("sun_azimuth")); Elevation=Solar->GetNumberField(TEXT("sun_elevation")); }
    for(TActorIterator<ADirectionalLight> It(GetWorld());It;++It)
    {
        It->SetActorRotation(FRotator(-Elevation,Azimuth+180,0));
        auto Light=Cast<UDirectionalLightComponent>(It->GetLightComponent());
        Light->SetAtmosphereSunLight(true); Light->SetLightSourceAngle(.533);
        Light->SetIntensity(50000*FMath::Clamp((Elevation+.3)/8.,0.,1.));
    }
    UE_LOG(LogTemp,Display,TEXT("ARRIETTY_UE_WORLD_LOADED triangles=%lld sections=%d collision_sections=%d build=%s"),Total,Count,CollisionSections,*Meta->GetStringField(TEXT("build_number")));
    return true;
}
