# 世界制作とArriettyでの利用

実装の根拠は [2026-09-08の仕様](WORLD_SPEC_2026-09-08.md) です。
これは本日の仕様であり、今後の相談で変更できます。
この開発は `Arrietty-UE58-worlds` worktreeで行い、フィットネス用の元チェックアウトには適用していません。

## 制作と実行の分離

制作元のUEプロジェクトにEditor用のArrietty Exporterを入れます。
利用者が制作物を保存し、Toolsメニューから明示的に書き出します。
Arriettyの通常起動は、検証と読み込みだけを行います。自動再エクスポートはしません。

```text
Documents/Unreal Projects/newYork/   制作元（インポーターは読み取りだけ）
                 ↓ 利用者が保存してExport
Documents/Arrietty Projects/newYork/
    world.json                      固定名の入口・元参照・整合性情報
    world-<書き出しID>.pak           Windows用にCookした世界
                 ↓ 起動前の整合性検証
Arrietty実行版 ＋ 起動ごとの新しいセッション
```

DocumentsはWindowsのドキュメントフォルダーを解決するため、リダイレクトにも対応します。
出力フォルダー名は制作元のディレクトリ名です。同名で別の元プロジェクトが既に登録されていれば上書きを拒否します。
Unreal Projects直下に準備用プロジェクトや出力ディレクトリは追加しません。

## 最初の準備

このworktreeで、Windows x64 / UE 5.8.2 / CPython 3.13を使います。

```powershell
.\tools\package_runtime.ps1
```

`build/runtime/Windows` にエディター不要のDevelopment実行版を作ります。
本体の機能を変更した場合は、このパッケージを更新します。
世界だけの変更で本体を再ビルドする必要はありません。

制作元のエディターを閉じてから、対象を明示してプラグインをインストールします。

```powershell
$documentsRoot = [Environment]::GetFolderPath('MyDocuments')
py -3.13 tools/install_world_exporter.py (Join-Path $documentsRoot 'Unreal Projects\newYork\newYork.uproject')
```

インストーラーが変更するのは、指定した制作元の `Plugins/ArriettyExporter` と
`.uproject` のプラグイン登録です。初回の `.uproject` は `.uproject.before-arrietty` として保存します。
Engineのインストール先は変更しません。任意の既存プロジェクトへ勝手に一括インストールしません。

## 世界の書き出し

1. 制作元プロジェクトをUEエディターで開き、使用するマップを開きます。
2. 制作した変更をすべて保存します。
3. **Tools → Export saved world to Arrietty** を実行します。
4. 完了メッセージに出る `world.json` をArriettyの起動に指定します。

保存していない変更があればエラーです。出発点はPlayerStartの位置・yawです。
複数ある場合は一つだけに `ArriettyStart` タグを付けます。ない場合は原点・yaw 0を使用します。
実際の走行前方は、従来どおり開始時Button 1で確認したHMD水平前方です。

エクスポーターは保存済みアセットの依存関係を調べ、必要な入力だけを出力側の作業場所へ一時収集します。
UEのバッチ処理でCookし、UE標準の `.pak` にまとめ、成功後だけJSONを更新します。
未使用の制作データや制作用エクステンションのバイナリは世界パックへコピーしません。
元のContentにある未Cookアセットは、実行時に直接読める形式とは扱いません。
新しい書き出しの変換エラーは `export-cook.log` / `export-pak.log` で確認できます。
成功時は一時的な入力コピーを削除します。失敗時は診断用の `.work-<ID>` が残る場合があります。
過去のpakは現在のworld.jsonから参照されません。不要な過去版・失敗時の作業ディレクトリは、
その世界を実行していないときに削除できます。元プロジェクトのデータは削除対象ではありません。

## 起動

```powershell
.\start.ps1 -WorldManifest (Join-Path $documentsRoot 'Arrietty Projects\newYork\world.json')
```

実機ではSteamVRを先に起動し、他のArrietty/UPBGEを終了してください。
新経路の既定UDPは19859です。元のフィットネス環境の19858を使いません。
既知の別Arriettyが動いている場合は、新しい実機セッションを拒否します。

実機に接続しない確認:

```powershell
.\start.ps1 -WorldManifest (Join-Path $documentsRoot 'Arrietty Projects\newYork\world.json') -Offline
```

起動時に、本体の実行ファイルとpak、元の保存データ、変換済みデータ、対応するUE/描画設定を照合します。
元Content/Config/Source等の保存データの変更・追加・削除も不一致です。
元データを変更したら、利用者が保存して再エクスポートしてください。
元データに不整合があれば起動エラーとし、古い世界への自動復帰はしません。
元の制作プロジェクトを移動した場合も、その場所から再エクスポートします。

`.runtime/world-sessions/<ID>` に、その回だけのセッション、ユーザー設定、CSV、ログ、画面保存を置きます。
毎回新しいIDを使い、前回の位置・実行時保存を引き継ぎません。
本体・世界データを書き換えず、機器設定 `settings.local.json` と過去の運動記録は保持します。
別の土地を飛ぶ場合は終了し、別の `world.json` を指定して起動します。
ゲーム内の土地選択画面や飛行中のシームレスな移動は今回の実装に含めていません。

従来のツバル経路は `.\start-ue.ps1`（WorldManifestなし）で利用できます。
こちらは既存のSecret-Worldを使うEditor standalone経路です。

## 対応範囲と検証の区別

- 世界はUEネイティブの保存済みマップと依存アセットとして渡します。
  データの参照関係を保ち、同じUEビルドとArriettyの描画設定でCookします。
- 本体にない実行用のC++クラスなどが必要な場合はエラーです。
  制作エクステンションの実行時依存は自動で持ち込みません。
  焼き込み可能な結果へ制作側で変換するか、将来の本体対応として扱います。
- 外部世界の光源・空・ポストプロセスはマップの設定を保持します。
  ツバルの太陽位置計算を外部世界へ適用せず、専用日時UIを隠します。
- 本体の固定アセットと同じパッケージ名は使用できません。該当する名前をエラーで知らせます。
- 出発点からの高度0を地上とする従来の飛行計算を保持しています。
  山の斜面に沿った走行・任意地形への着陸や障害物との衝突応答の追加ではありません。
- スタティックメッシュ、制作元のマテリアル、太陽・空、ポストプロセス、異なる出発点・yawを含む
  2つの小さな世界で、同じ実行版による読み込み・走行・離陸・終了と画面を確認しました。
  Landscape、World Partition、Niagara、Sequencer等の個別実機対応を検証済みとは扱いません。
- エクスポーターはUE標準のCookを利用します。起動検査だけで、あらゆる世界のVR性能や
  全ての実行時不具合が保証されるものではありません。HMD実機での受け入れは別途必要です。

## 開発用検証

```powershell
py -3.13 -m unittest discover -s tests
.\tools\test_ue.ps1 -Smoke
py -3.13 tools/test_world_pipeline.py --name City
py -3.13 tools/test_world_pipeline.py --name Island
py -3.13 tools/test_world_rejection.py
py -3.13 tools/check_public_tree.py
```

パイプライン試験はこのworktreeの `build/world-fixtures` に使い捨ての制作プロジェクトを作ります。
既存のDocuments内の制作物は触らず、機器にも接続しません。
外部世界試験のポートは29859、ツバル回帰試験は29858です。
生成物、エクスポートJSONに含む個人のパス、バイナリ、ログ、セッションはGitへ追加しません。
