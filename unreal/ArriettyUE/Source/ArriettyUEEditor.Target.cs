using UnrealBuildTool;
public class ArriettyUEEditorTarget : TargetRules
{
    public ArriettyUEEditorTarget(TargetInfo Target) : base(Target)
    {
        Type = TargetType.Editor;
        DefaultBuildSettings = BuildSettingsVersion.V7;
        IncludeOrderVersion = EngineIncludeOrderVersion.Unreal5_8;
        ExtraModuleNames.Add("ArriettyUE");
    }
}
