#include "ArriettyGameInstance.h"
#include "HAL/PlatformFileManager.h"
#include "IPlatformFilePak.h"
#include "Misc/FileHelper.h"
#include "Misc/PackageName.h"
#include "Misc/Paths.h"
#include "Serialization/JsonSerializer.h"

void UArriettyGameInstance::Init()
{
    Super::Init();
    FString Data;
    TSharedPtr<FJsonObject> Session;
    const FString Path=FPlatformMisc::GetEnvironmentVariable(TEXT("ARRIETTY_UE_SOLAR"));
    if(Path.IsEmpty() || !FFileHelper::LoadFileToString(Data,*Path) ||
       !FJsonSerializer::Deserialize(TJsonReaderFactory<>::Create(Data),Session) || !Session.IsValid()) return;
    FString PakPath;
    if(!Session->TryGetStringField(TEXT("world_pak"),PakPath)) return;
    auto Pak=static_cast<FPakPlatformFile*>(FPlatformFileManager::Get().FindPlatformFile(TEXT("PakFile")));
    if(!Pak || !Pak->Mount(*PakPath,100))
    {
        UE_LOG(LogTemp,Error,TEXT("ARRIETTY_WORLD_MOUNT_FAILED"));
        FPlatformMisc::RequestExitWithStatus(true,1);
        return;
    }
    const TArray<TSharedPtr<FJsonValue>>* Mounts;
    if(Session->TryGetArrayField(TEXT("content_mounts"),Mounts))
        for(const auto& Value:*Mounts)
        {
            const FString Name=Value->AsString();
            if(Name.IsEmpty() || Name.Contains(TEXT("/")) || Name.Contains(TEXT("\\")) || Name.Contains(TEXT(".")) || Name==TEXT("Game") || Name==TEXT("Engine"))
            {
                UE_LOG(LogTemp,Error,TEXT("ARRIETTY_WORLD_INVALID_MOUNT"));
                FPlatformMisc::RequestExitWithStatus(true,1); return;
            }
            FPackageName::RegisterMountPoint(TEXT("/")+Name+TEXT("/"),FPaths::ProjectPluginsDir()/Name/TEXT("Content/"));
        }
    UE_LOG(LogTemp,Display,TEXT("ARRIETTY_WORLD_MOUNTED"));
}
