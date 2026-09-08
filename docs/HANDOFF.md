# 開発の記憶・引き継ぎ

更新日: 2026-09-08（日本時間）。

## 本日の世界制作分離の実装依頼（2026-09-08）

**開発は別worktree `Arrietty-UE58-worlds` / `work/world-export-20260908` で行う。**
元の `Arrietty-UE58` はフィットネス実運用中。元のコード・生成物・設定・ログ・
セッションを変更せず、マージや実機起動もしない。テストの通信ポートも分離する。

先に [本日の仕様](WORLD_SPEC_2026-09-08.md) を読むこと。
利用者は相談後、仕様をcompactに耐える文書に残してから実装するよう依頼した。
以前の「実装不可」はこの依頼で解除された。コード変更・オフライン検証を進めてよい。
制作元プロジェクト内のEditorプラグインから、利用者が明示的に書き出すB案。
出力は `Documents/Arrietty Projects/<制作元フォルダー名>/world.json` と変換済みファイル。
元参照との不整合はエラー。通常起動で自動再エクスポートや古い世界への自動復帰はしない。
これは本日の仕様であり、明日以降の利用者の新しい指示に従って変更できる。
この段落や本日の仕様を、将来の変更を拒む根拠にしない。
新経路はworktreeで実装済み。[使い方](WORLDS.md) と [検証記録](VALIDATION.md) を参照する。
JSON + Cook済みpakを外部から読み込み、起動ごとにセッションを分離する。
同じWindows実行版で2世界の走行・離陸・終了、旧Tuvalu回帰、Python 103件とUEネイティブ2件が成功。
初回は試験プロジェクトで検証し、その後、利用者指定の独立した制作元Funafutiにも配置した。
実機確認・元checkoutへの適用は未実施。
利用者の追加依頼により `install-world-exporter.ps1 <プロジェクトフォルダー名>` を追加。
制作元はユーザープロファイルの `Documents/Unreal Projects` 直下を前提とする。
指定フォルダー内の唯一の `.uproject` を既存Pythonインストーラーへ渡す。

## Funafutiの編集用プロジェクト（2026-09-08追加依頼）

利用者は `Documents/Unreal Projects/Funafuti` を作り、現在の地形を編集可能にするよう依頼した。
その後は利用者がCinderLinkで美観を改善し、保存・明示的Export・Arriettyでのテストを行う順序。
FunafutiのExportと実機テストを先回りして実行しない。

- 作成先: `C:/Users/azoo/Documents/Unreal Projects/Funafuti/Funafuti.uproject`。
  開始マップは `/Game/Worlds/Funafuti/Maps/Funafuti`。
- 元の実運用Content/SecretWorldを読み取り、ハッシュ確認後、664個の保存済みStatic Meshへ変換した。
  428,029三角形、32マテリアルインスタンス、海のテクスチャ、元の夕景、PlayerStartを保持。
  Landscapeではなく、元の描画区画・マテリアル単位のメッシュ。全建物が一棟ずつではない。
- Engineに設置済みのCinderLinkとプロジェクト内のArrietty Exporterを有効化。
  CinderLinkのモデル会話は開始していない。プロジェクト内のREADME-Arrietty.md / AGENTS.mdに
  美観の編集・書き出し手順と原データクレジットを残した。
- 再開・検証用: `tools/prepare_funafuti_authoring.py`（既存の制作先は上書き拒否）、
  `tools/build_funafuti_authoring.py`、`tools/verify_funafuti_authoring.py`。
  原データの一時コピーはworktreeの `build/funafuti-authoring-input`。生成UEアセットはGit対象外。
  海の再インポート原本は制作プロジェクト内の `SourceArt/reef.tga` に保持。
- 保存後の再読み込みで全メッシュ・三角形数・配置を検証。境界座標の最大誤差0.125cm。
  地形ActorはUE標準クラスのみで、実行用プラグインの追加mount依存は0。
- テクスチャのInterchange編集用参照を実行用依存と誤判定する問題を発見し、
  ExporterがUEのGame参照だけを辿るよう修正。別のCity fixtureでインポート画像の
  Cook・pak・同じArrietty実行版での走行を確認した。Funafuti自体は未Export。

同日、利用者から「Toolsにexportがあった」「README-Arrietty.mdを読んだ」
「CinderLink内にCodexが表示された」「大丈夫そう」との確認を受領した。
これは利用者による制作環境の表示確認。美観編集・FunafutiのExport・実機試験の完了報告とは区別する。
次回はこの制作プロジェクトで美観の編集から再開できる。

## 運用開始時点

利用者から「今晩から本気でつかえます」との運用開始判断を受領し、
ドキュメントと記憶を残してpushする依頼に対応した。
運用開始時点の実装は [`b3b0cc1`](https://github.com/ysk424/Arrietty-UE58/commit/b3b0cc1)。
詳しい検証範囲は [VALIDATION.md](VALIDATION.md) に記載する。
これは利用者の運用開始判断の記録であり、全機器の個別試験を完了したという意味ではない。

## リポジトリと公開範囲

- UE版は独立した公開リポジトリ [ysk424/Arrietty-UE58](https://github.com/ysk424/Arrietty-UE58)。
  利用者の指定は「別のリポで別プッシュ」。UE版の変更はこのリポジトリで完結させる。
- 移植元は隣接する `../Arrietty-UP` の `b1a82dfc3624ec3dbb71bec088289b6fcec1a03c`。
  必要なPython実行コードはコピー済みで、移植元のチェックアウトは起動に不要。
- 風景と太陽位置計算は `../Secret-World` が供給する。準備スクリプトで最新の
  検証済みRuntimeを選び、元の `.blend` を変更せず書き出す。
- 公開するのはソース、再構築スクリプト、テスト、文書。同梱wheelの権利表記も維持する。
  個人の機器ID、`settings.local.json`、セッショントークン、ログ、生成風景、UEバイナリは
  Git対象外。機器IDを文書や記憶へ転記しない。

## 確定した操作仕様

1. SteamVRを起動し、同じ機器を使うUPBGE版を終了して `./start-ue.ps1` を実行する。
2. 必要ならツバル現地日時（UTC+12）を編集してApplyし、**P**で機器準備を始める。
3. **HMDで自転車の正面を見て、ハンドルを中央にしてButton 1を押す。**
   その瞬間に見ている方向を水平面へ投影し、前進方向（利用者の説明では＋X）として固定する。
4. 以後の旋回はハンドルで行う。首を左右に向けても進路は変えない。
5. 正面の再設定は **R**。今見ている方向を新しい前進方向として記録し、位置と経過時間を維持する。
   走行開始後の **Button 1は約2mの安全復帰**であり、再設定操作ではない。
6. **Esc**で機器停止・ログ保存・準備画面へ戻る。ウィンドウを閉じるとUEとブリッジが終了する。

Button 2は地上／飛行、Button 3・4はロール、3+4はピッチアップ、Button 6は押下中の負荷。
全操作は [README.md](../README.md) にまとめてある。心拍計の接続は走行開始条件ではない。

## 進行方向の修正を戻さないための記録

当初は風景の滑走路方位にHMDの視線を合わせていた。利用者から後方・斜め後方、
続いて右斜め前方へ進むとの報告があり、最終的に「開始時にHMDの正面を見てButton 1」
という基準を確認した。現在は **見ている方向へ自転車の進行方位を合わせ、視線を維持する**。
滑走路方位は開始前の初期値にすぎず、開始後の前進方向として強制しない。

- UEの `AArriettyPawn::CalcCamera` が、実際のカメラのワールド前方ベクトルをXY面へ投影する。
  車両のyawをその方位へ変え、Trackingの相対回転を組み直して視線のワールド回転を維持する。
- `alignment_bearing` と `aligned` をPythonへ送り、最初の移動より前に方位を一度だけ確定する。
  ブリッジは `alignment_applied` を返す。古い返信が開始前の方位を復元しないようUEで待ち合わせる。
- HMD/VIVEの有効な追跡と整列確認が移動の条件。新しい走行ではButton 1より前に整列を要求しない。
- 観測したずれを固定角度で補正しない。OpenXRの生の座標変換をUEの変換へ重ねて適用しない。
  `GetCameraView` 後のカメラと実際の移動方向で検証する。

座標は内部ENUメートルからUEセンチメートルへ `(north*100, east*100, altitude*100)`。
内部headingからUE yaw／地理方位は `(180-heading)%360`、機首上げはUE正pitch、
内部の左バンク正はUE負roll。詳しくは [PORT.md](PORT.md) を参照する。

## 環境・検証・再開時の参照先

- UE **5.8.2**（changelist 56702186）、Windows x64、Python **3.13**。
  元のフィットネス環境はUE Editor standalone。新しいworktreeの世界経路はWindows Development実行版。
- 2026-09-07の風景はSecret World Runtime **20260905102318005**。
  1,409メッシュ、428,029三角形、664描画セクション。更新時は最新版選択とハッシュ検証を使う。
- C++は描画・OpenXR・計器・日時UI、独立Pythonブリッジは既存の走行／飛行計算と機器処理を担当。
  UDPは認証付きloopback、既定ポート19858。1秒の受信断で機器停止処理に入る。
- `6502e50`: Windows PowerShell 5.1で空の `--date` 引数が消える問題を修正。
  日付未指定時はオプション自体を省く。5.1と7の引数回帰テストを維持する。
- `5bf08bd`: 描画カメラによる整列確認、R、視線診断ログを追加。
- `b3b0cc1`: HMDの開始時視線を前進方位として確定し、視線維持・古い姿勢返信の抑止を実装。
- 運用開始時の検証: **84件のPythonテスト、UEネイティブ2件、オフラインの走行・離陸・終了が成功**。
  心拍計は当時未接続。ファン・PTTなどの全組合せ試験やVR性能測定の完了を推定しない。

```powershell
.\tools\prepare_ue.ps1       # 最新風景の書き出し、C++、UEコンテンツ生成
.\tools\test_ue.ps1 -Smoke   # 実機へ接続しない回帰・UE検証
py -3.13 tools\check_public_tree.py  # stage済みの公開内容を確認
```

実機ログは `logs/latest-ue-flight.csv`、模擬ログは `logs/latest-ue-offline.csv`。
UEの `ARRIETTY_UE_HMD_ALIGNED` / `ARRIETTY_UE_VIEW` とブリッジの `ARRIETTY_UE_FORWARD` で
視線・車両方位・確定方位を比較できる。起動で上書きされる診断ログは、調査に必要なら先に保管する。
生成物や既存の実機セッションを文書更新のために再生成・再起動する必要はない。

## 夜の実機運用で判明したこと（2026-09-07）

南へ飛ぶと「透明な壁」があるように止まるとの報告は、ハンドル用VIVEの追跡切れと
結びついた。20:14〜20:15のログは記録自体が継続し、HMD追跡も有効なまま、
約14秒など複数回にわたり位置・高度・飛行状態が固定されていた。

利用者による原因の特定: ライトハウスは4台あるが、ハンドルVIVEから見えるのは1台だけで、
それが体で遮られる。利用者は **2台が見える配置にする** 方針を決めた。配置変更後の結果は未報告。

ハンドル前方のSurface Studioの画面反射も疑い、画面を布で覆う対策を利用者が提案した。
反射面を覆う方法は [VIVE公式の案内](https://blog.vive.com/us/roomscale-101/) にもある。
反射対策と、体や画面に遮られない直接の見通しの確保を併せて確認する。
Surface Studioの反射が今回の停止に寄与したか、布で改善したかはまだ未確認。

**ソフトの停止条件は変更していない。** VIVE追跡切れ時に飛行を中立舵で続行する案は
実装せず、まず見通しの改善で確認する。調査中の実機セッションも再起動していない。
飛行状態が止まることとCSV書き込みが止まることを混同しない。
詳細な時刻と座標は [VALIDATION.md](VALIDATION.md) の夜の実機記録を参照する。
