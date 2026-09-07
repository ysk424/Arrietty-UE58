using UnrealBuildTool;
public class ArriettyUE : ModuleRules
{
    public ArriettyUE(ReadOnlyTargetRules Target) : base(Target)
    {
        PCHUsage = PCHUsageMode.UseExplicitOrSharedPCHs;
        PublicDependencyModuleNames.AddRange(new[] { "Core", "CoreUObject", "Engine", "InputCore", "HeadMountedDisplay", "XRBase", "Sockets", "Networking", "Json", "UMG", "Slate", "SlateCore", "ProceduralMeshComponent" });
    }
}
