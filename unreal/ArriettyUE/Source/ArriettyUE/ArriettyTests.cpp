#include "CoreMinimal.h"
#include "Misc/AutomationTest.h"

#if WITH_DEV_AUTOMATION_TESTS
IMPLEMENT_SIMPLE_AUTOMATION_TEST(FArriettyAttitudeTest,"Arrietty.Coordinates.Attitude",EAutomationTestFlags::EditorContext|EAutomationTestFlags::EngineFilter)
bool FArriettyAttitudeTest::RunTest(const FString&)
{
    // Tests physical nose/wing directions, independent of Python conversion.
    TestTrue(TEXT("UE positive pitch raises nose"),FRotator(6,0,0).RotateVector(FVector::ForwardVector).Z>0);
    TestTrue(TEXT("Left bank converted to UE -roll lowers left wing"),FRotator(0,0,-10).RotateVector(FVector(0,-1,0)).Z<0);
    TestTrue(TEXT("Right bank converted to UE +roll lowers right wing"),FRotator(0,0,10).RotateVector(FVector(0,1,0)).Z<0);
    TestTrue(TEXT("North points +X"),FRotator(0,0,0).Vector().Equals(FVector(1,0,0),1.e-6));
    TestTrue(TEXT("East points +Y"),FRotator(0,90,0).Vector().Equals(FVector(0,1,0),1.e-6));
    return true;
}
#endif
