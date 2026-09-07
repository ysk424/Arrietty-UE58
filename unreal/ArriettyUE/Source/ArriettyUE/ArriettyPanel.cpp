#include "ArriettyPanel.h"
#include "Dom/JsonObject.h"
#include "Rendering/DrawElements.h"
#include "Styling/CoreStyle.h"

int32 UArriettyPanel::NativePaint(const FPaintArgs& Args, const FGeometry& G,
    const FSlateRect& Culling, FSlateWindowElementList& E, int32 L,
    const FWidgetStyle& Style, bool Enabled) const
{
    const FSlateBrush* Brush = FCoreStyle::Get().GetBrush("WhiteBrush");
    auto Box = [&](float X,float Y,float W,float H,FLinearColor C) {
        FSlateDrawElement::MakeBox(E,L,G.ToPaintGeometry(FVector2f(W,H),FSlateLayoutTransform(FVector2f(X,Y))),Brush,ESlateDrawEffect::None,C);
    };
    auto Text = [&](float X,float Y,const FString& S,int32 Size,FLinearColor C=FLinearColor::White) {
        FSlateDrawElement::MakeText(E,L+2,G.ToPaintGeometry(FVector2f(1500,540),FSlateLayoutTransform(FVector2f(X,Y))),S,FCoreStyle::GetDefaultFontStyle("Regular",Size),ESlateDrawEffect::None,C);
    };
    auto Line = [&](FVector2f A,FVector2f B,FLinearColor C,float Width=2) {
        TArray<FVector2f> Points{A,B};
        FSlateDrawElement::MakeLines(E,L+1,G.ToPaintGeometry(),Points,ESlateDrawEffect::None,C,true,Width);
    };
    Box(0,0,1500,540,FLinearColor(.009,.014,.024,1));
    Box(16,62,402,452,FLinearColor(.022,.032,.048,1));
    Box(430,62,610,452,FLinearColor(.018,.025,.04,1));
    Box(1052,62,432,452,FLinearColor(.022,.032,.048,1));
    Text(24,12,TEXT("ARRIETTY  /  HUMAN POWERED FLIGHT"),22,FLinearColor(.3,.9,.85));
    Text(900,16,Status,17,FLinearColor(1,.8,.35));
    if (!bPlaying || !Telemetry.IsValid())
    {
        Text(60,100,TEXT("FUNAFUTI / TUVALU"),32);
        Text(60,165,TEXT("P  Start simulator"),24);
        Text(60,215,TEXT("Button 1  Align HMD + centered VIVE handle"),22);
        Text(60,265,TEXT("Button 2  Ground / flight    Button 6  Brake"),22);
        Text(60,315,TEXT("Button 3 / 4  Roll    Both  Pitch up"),22);
        Text(60,365,TEXT("Button 5  PTT    Esc  Return to setup"),22);
        Text(60,408,TEXT("R  Realign HMD + centered handle during a ride"),22);
        Text(60,450,TEXT("Secret World | OpenStreetMap contributors / ODbL | Allen Coral Atlas / CC BY 4.0"),14);
        return L+3;
    }
    const TSharedPtr<FJsonObject>* R = nullptr;
    Telemetry->TryGetObjectField(TEXT("readout"), R);
    auto S = [&](const TCHAR* Key) { FString V; if(R) (*R)->TryGetStringField(Key,V); return V; };
    auto N = [&](const TCHAR* Key) { double V=0; Telemetry->TryGetNumberField(Key,V); return V; };
    Text(38,80,TEXT("HEART RATE      POWER"),20,FLinearColor(.6,.7,.8));
    Text(38,118,S(TEXT("heart_rate"))+TEXT("    ")+S(TEXT("trainer_power")),52);
    Text(38,190,TEXT("bpm                  watts"),19,FLinearColor(.6,.7,.8));
    Text(38,240,TEXT("GROUND   ")+S(TEXT("ground_speed")),25);
    Text(38,292,TEXT("GRADE     ")+S(TEXT("trainer_grade")),25);
    Text(38,350,S(TEXT("mode")),30,FLinearColor(.35,1,.6));
    Text(38,420,TEXT("ELAPSED  ")+S(TEXT("elapsed_time")),25);
    const float CX=735,CY=305,Radius=145;
    const double Bank=FMath::DegreesToRadians(N(TEXT("bank")));
    const double Pitch=N(TEXT("pitch"))*3;
    // Analytic circular aperture, including +/-90 degree bank; no HMD shader mask.
    for(float Y=-Radius;Y<Radius;Y+=2)
    {
        const float Half=FMath::Sqrt(FMath::Max(0.f,Radius*Radius-Y*Y));
        const auto Sky=FLinearColor(.025,.23,.48),Earth=FLinearColor(.25,.10,.035);
        const double A=-FMath::Sin(Bank), B=FMath::Cos(Bank)*Y-Pitch;
        if(FMath::Abs(A)<1.e-6) Box(CX-Half,CY+Y,2*Half,2,B<0?Sky:Earth);
        else
        {
            const float Cut=FMath::Clamp(float(-B/A),-Half,Half);
            Box(CX-Half,CY+Y,Cut+Half,2,A>0?Sky:Earth);
            Box(CX+Cut,CY+Y,Half-Cut,2,A>0?Earth:Sky);
        }
    }
    for(int D=-30;D<=30;D+=10)
    {
        const double Offset=Pitch-D*3;
        if(FMath::Abs(Offset)>110) continue;
        const float W=D==0?70:30;
        FVector2f A(-W,Offset),B(W,Offset);
        auto Rot=[&](FVector2f P){return FVector2f(CX+P.X*FMath::Cos(Bank)-P.Y*FMath::Sin(Bank),CY+P.X*FMath::Sin(Bank)+P.Y*FMath::Cos(Bank));};
        Line(Rot(A),Rot(B),FLinearColor::White,D==0?3:1);
    }
    Line({CX-55,CY},{CX-16,CY},FLinearColor(1,.85,.1),4);
    Line({CX+16,CY},{CX+55,CY},FLinearColor(1,.85,.1),4);
    Line({CX-16,CY},{CX,CY+10},FLinearColor(1,.85,.1),4);
    Line({CX,CY+10},{CX+16,CY},FLinearColor(1,.85,.1),4);
    Text(676,78,S(TEXT("heading"))+TEXT(" deg"),28);
    const double Heading=N(TEXT("heading"));
    for(int D=-60;D<=60;D+=30)
    {
        const float X=CX+D*3;
        Text(X-20,123,FString::Printf(TEXT("%03.0f"),FMath::Fmod(Heading+D+360,360)),16);
        Line({X,147},{X,154},FLinearColor::White);
    }
    Text(CX+FMath::Clamp(N(TEXT("home_relative")),-80.,80.)*3-8,154,S(TEXT("home_marker")),20,FLinearColor(1,.15,.8));
    Text(447,216,TEXT("AIR"),18); Text(447,253,S(TEXT("airspeed")),38);
    Text(447,316,TEXT("km/h"),17); Text(445,401,S(TEXT("stall_speed")),18,FLinearColor(1,.2,.16));
    Text(921,216,TEXT("ALT"),18); Text(910,253,S(TEXT("altitude")),32);
    Text(945,316,TEXT("m"),17);
    Text(630,474,S(TEXT("pfd_status")),21,FLinearColor(.4,1,.65));
    Text(1070,76,S(TEXT("physics")),18);
    Text(1070,273,S(TEXT("debug")),15,FLinearColor(.7,.83,.9));
    return L+3;
}
