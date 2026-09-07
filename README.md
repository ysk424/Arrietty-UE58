# Arrietty-UE58

**2026-09-08の開発:** 世界制作を別UEプロジェクトへ分けるEditorエクスポーターと、
外部世界を読むエディター不要の実行経路を追加しています。
[本日の仕様](docs/WORLD_SPEC_2026-09-08.md) と [世界の書き出し・起動手順](docs/WORLDS.md) を参照してください。
この変更は別worktreeで開発し、フィットネス用の元チェックアウトへは適用していません。

Arrietty-UPの実機確認済みの自転車・人力飛行シミュレーターを、Unreal Engine
5.8.2の描画・OpenXR・VR計器へ移植したWindows向けプロジェクトです。
地上の風景には、隣接するSecret-Worldの最新の検証済みRuntimeを使用します。

UEのC++が描画・HMD・計器・日時設定を担当し、独立したPythonプロセスが
既存の飛行計算とBLE・シリアル・VIVE操舵・ファン・音声PTTを担当します。
PythonをUEの描画フレームへ埋め込まず、認証トークン付きlocalhost UDPで
姿勢と計器値を渡します。このリポジトリだけに実行コードを含み、Arrietty-UPの
チェックアウトは起動に必要ありません。

**状態（2026-09-07）:** 利用者から「今晩から本気でつかえます」との運用開始判断を
受領しました。運用開始時点の実装は [`b3b0cc1`](https://github.com/ysk424/Arrietty-UE58/commit/b3b0cc1) です。
C++ビルド、84件のPythonテスト、UEの座標・HMDカメラ検証、実機を使わない
走行・離陸・終了を確認済みです。確認済みの内容と心拍計などの継続確認項目は
[検証記録](docs/VALIDATION.md)に、確定仕様と開発の記憶は
[引き継ぎメモ](docs/HANDOFF.md)に記録しています。

## 準備

- Windows x64、Unreal Engine **5.8.x**、対応するVisual C++ツールチェーン。
- CPython **3.13 x64**とPython Launcher (`py -3.13`)。
- SteamVR/OpenXRと対応HMD。実機なしの確認では不要です。
- `../Secret-World` の `build/runtime/*.runtime.json` と対応する `.blend`。
  この公開Gitには生成済みの風景やUEのバイナリを含めません。
- 風景出力用のBlender/UPBGE。既定は隣接する既存のUPBGEビルドです。

```powershell
.\tools\prepare_ue.ps1
```

別のインストール先は引数で指定できます。

```powershell
.\tools\prepare_ue.ps1 -EngineRoot 'D:\Epic Games\UE_5.8' `
  -BlenderPath 'D:\UPBGE\blender.exe' -WorldRoot '..\Secret-World'
```

最新RuntimeのSHA-256を確認して風景を書き出し、C++をビルドし、マテリアルと
`Funafuti.umap`を生成します。元の `.blend` は保存・変更しません。

## 起動

```powershell
.\start-ue.ps1 -Offline       # 実機へ接続しない確認
.\start-ue.ps1                # SteamVRと実機を使う
```

起動時は日時設定画面です。ツバル現地日付・時刻（UTC+12）を編集し、
**Apply local date / time** を押してから **Start simulator / P** で開始します。
未適用の日時では開始できません。世界の時刻はプレイ中に進みません。
Escで準備画面へ戻ると日時を変更できます。ウィンドウを閉じると終了します。

```powershell
.\start-ue.ps1 -LocalDate 2026-09-07 -LocalTime 17:45
```

Pを押すまで実機サービスは始まりません。Pの後、HMDを自転車の正面へ向け、
VIVEハンドルを中央にして **Button 1** で整列・走行開始します。
この瞬間に見ている方向を水平面へ投影し、自転車の前進方向として固定します。
開始時に風景を回さず、その後はハンドルで曲がります。首だけを左右に向けても
進路は変わりません。開始後に正面を合わせ直したい場合は、
ペダリングを止め、自転車の正面を向き、ハンドルを中央にして **R** で合わせ直せます。
走行中のButton 1は安全復帰の操作です。正面を合わせ直す場合はRを使ってください。
HMD姿勢やVIVE追跡が無効な間は移動と風量を止めます。
心拍計の接続は走行開始の条件ではありません。

| 操作 | 動作 |
|---|---|
| Button 1 | HMD/VIVE整列・開始、開始後は約2mの安全復帰 |
| R | 今見ている方向を新しい前進方向として記録し、ハンドル中央を合わせ直す。位置と経過時間を維持 |
| Button 2 | 地上／人力飛行。空中では地上モードへ戻せません |
| Button 3 / 4 | 左／右ロールを1度変更 |
| Button 3 + 4 | 80ms以内の同時押しでピッチを1度上げる |
| Button 5 | 既存UDP音声ブリッジのPTT |
| Button 6 | 押下中のT2負荷3% |
| Joystick 2 | 中央から倒す1操作でピッチ／ロールを1度変更、SWでリセット |
| Joystick 1 | SWで飛行調整を選択・確定、左右で値を調整 |
| Esc | 機器停止・CSV保存・日時設定に戻る |

Offlineモードだけは、上／下矢印で模擬速度、左右矢印で操舵、数字列1〜8で
操作盤の各ビットを入力できます。数字3+4で離陸用のピッチを上げます。
実機モードの運転操作は有線操作盤を使用します。

## 機器設定

`settings.example.json`を`settings.local.json`へコピーし、自分のT2のBLEアドレスと
VIVEハンドルのシリアルを指定できます。空欄ならT2広告を検索し、最初のVIVE
コントローラーを操舵として選びます。複数コントローラーではシリアル指定を推奨します。
環境変数 `ARRIETTY_TRAINER_ADDRESS` / `ARRIETTY_STEERING_SERIAL` でも設定できます。
`settings.local.json`とセッショントークンはGit対象外です。

BLE/OpenVR依存は同梱wheelから `.runtime` へ展開し、システムPythonを変更しません。
ESP32ファンは従来どおり `192.168.4.1:4210`、音声PTTは `127.0.0.1:49000` です。
音声認識・読み上げサーバー自体は、このリポジトリには含めていません。

## ログと検証

- 実機フライト: `logs/latest-ue-flight.csv`、約10Hz、次のPで上書き。
- 模擬フライト: `logs/latest-ue-offline.csv`。実機ログとは別です。
- UE／通信診断: `logs/latest-ue.log`、`logs/latest-ue-bridge*.log`。
- UEログの `ARRIETTY_UE_HMD_ALIGNED` は描画カメラ確認後の正面合わせ、
  `ARRIETTY_UE_VIEW` は1秒ごとの視線・自転車・HMDの向きを記録します。
- CSVは既存のENU座標・日時・高度・pitch/roll形式を維持します。

```powershell
.\tools\test_ue.ps1          # Python、風景ハッシュ、UEの座標検証
.\tools\test_ue.ps1 -Smoke   # 上記と、実機なしのUE描画・離陸・終了
```

ソース構成・プロトコル・運用開始時点の検証は
[移植仕様](docs/PORT.md)と[検証記録](docs/VALIDATION.md)を参照してください。
ライセンスは[MIT](LICENSE)。外部ソフトウェアと地理データの条件は
[Third-party notices](THIRD_PARTY_NOTICES.md)に記載しています。
