#include "ArriettySetup.h"
#include "ArriettyPawn.h"
#include "Widgets/Layout/SBorder.h"
#include "Widgets/SBoxPanel.h"
#include "Widgets/Text/STextBlock.h"
#include "Widgets/Input/SEditableTextBox.h"
#include "Widgets/Input/SButton.h"
#include "Styling/CoreStyle.h"

TSharedRef<SWidget> UArriettySetup::RebuildWidget()
{
    const auto Font=FCoreStyle::GetDefaultFontStyle("Regular",16);
    return SNew(SBorder).Padding(24).BorderBackgroundColor(FLinearColor(.02f,.035f,.055f,.95f))
    [ SNew(SVerticalBox)
        +SVerticalBox::Slot().AutoHeight().Padding(0,0,0,15)
        [SNew(STextBlock).Text(FText::FromString(TEXT("ARRIETTY / FUNAFUTI"))).Font(FCoreStyle::GetDefaultFontStyle("Bold",22))]
        +SVerticalBox::Slot().AutoHeight().Padding(0,0,0,8)
        [SNew(STextBlock).Text(FText::FromString(TEXT("Tuvalu local date / time (UTC+12)"))).Font(Font)]
        +SVerticalBox::Slot().AutoHeight().Padding(0,0,0,8)
        [SNew(SEditableTextBox).Text_Lambda([this]{return FText::FromString(Pawn?Pawn->SetupDate:TEXT(""));})
            .HintText(FText::FromString(TEXT("YYYY-MM-DD"))).Font(Font)
            .OnTextChanged_Lambda([this](const FText& T){if(Pawn){Pawn->SetupDate=T.ToString();Pawn->bSetupDirty=true;}})]
        +SVerticalBox::Slot().AutoHeight().Padding(0,0,0,12)
        [SNew(SEditableTextBox).Text_Lambda([this]{return FText::FromString(Pawn?Pawn->SetupTime:TEXT(""));})
            .HintText(FText::FromString(TEXT("HH:MM"))).Font(Font)
            .OnTextChanged_Lambda([this](const FText& T){if(Pawn){Pawn->SetupTime=T.ToString();Pawn->bSetupDirty=true;}})]
        +SVerticalBox::Slot().AutoHeight().Padding(0,0,0,12)
        [SNew(SButton).Text(FText::FromString(TEXT("Apply local date / time")))
            .OnClicked_Lambda([this]{if(Pawn){++Pawn->ApplyId;Pawn->bSetupDirty=true;}return FReply::Handled();})]
        +SVerticalBox::Slot().AutoHeight().Padding(0,0,0,12)
        [SNew(STextBlock).AutoWrapText(true).Font(Font)
            .Text_Lambda([this]{return FText::FromString(Pawn?Pawn->SetupMessage:TEXT(""));})]
        +SVerticalBox::Slot().AutoHeight().Padding(0,0,0,12)
        [SNew(SButton).Text(FText::FromString(TEXT("Start simulator (P)")))
            .IsEnabled_Lambda([this]{return Pawn && !Pawn->bSetupDirty;})
            .OnClicked_Lambda([this]{if(Pawn)Pawn->StartSimulation();return FReply::Handled();})]
        +SVerticalBox::Slot().AutoHeight()
        [SNew(STextBlock).AutoWrapText(true).Font(FCoreStyle::GetDefaultFontStyle("Regular",12))
            .Text(FText::FromString(TEXT("Button 1: align and start\nEsc: return here to change the date/time\nClose the window to exit")))]
    ];
}
