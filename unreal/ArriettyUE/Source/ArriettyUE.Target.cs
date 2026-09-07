using UnrealBuildTool;
public class ArriettyUETarget : TargetRules
{
    public ArriettyUETarget(TargetInfo Target) : base(Target)
    {
        Type = TargetType.Game;
        DefaultBuildSettings = BuildSettingsVersion.V7;
        IncludeOrderVersion = EngineIncludeOrderVersion.Unreal5_8;
        ExtraModuleNames.Add("ArriettyUE");
    }
}
