# spiritual-shorts-factory

Instagram Reels URL またはローカル動画ファイルから、文字起こし、HeyGen アバター動画生成、SRT 字幕生成、CapCut ドラフト作成までをつなぐ macOS 向けの半自動パイプラインです。CapCut 連携はデスクトップ版 CapCut のローカル草稿フォルダを使います。

## セットアップ

### かんたんセットアップ

管理者権限がなく `brew` を使えない環境でも、ローカルに Python 3.10 と `ffmpeg` を用意できます。

```bash
bash scripts/bootstrap_env.sh
```

### 手動セットアップ

1. Python 3.10+ と `ffmpeg` / `ffprobe` をインストールします。
2. 仮想環境を作成して依存関係を入れます。
3. `.env.example` を `.env` にコピーして値を設定します。
4. `config/settings.yaml` を必要に応じて調整します。

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
cp .env.example .env
```

`scripts/bootstrap_env.sh` を使った場合は次で確認できます。

```bash
./.venv/bin/python --version
./.venv/bin/ffprobe -version
```

## Instagram 初期設定

URL からダウンロードする場合は、Chrome などで Instagram にログインした状態から `cookies.txt` を書き出し、`config/instagram_cookies.txt` に保存してください。

- `Get cookies.txt LOCALLY` のような拡張で `Netscape` 形式の `cookies.txt` を出力します
- 保存先は `config/instagram_cookies.txt` です
- 権限は `chmod 600 config/instagram_cookies.txt` を推奨します
- 詳細手順は `scripts/export_instagram_cookies.md` を参照してください

## 実行方法

いちばん簡単な入口:

```bash
bash scripts/run_pipeline.sh "https://www.instagram.com/reel/XXXXX"
```

`pip install -e .` 済みなら、インストールしたコマンドからも実行できます。

```bash
spiritual-shorts-factory "https://www.instagram.com/reel/XXXXX"
```

ローカル動画ファイルから開始:

```bash
python src/main.py inputs/sample.mp4
```

Instagram Reels URL から開始:

```bash
python src/main.py "https://www.instagram.com/reel/XXXXX"
```

詳細ログを有効化:

```bash
python src/main.py "https://www.instagram.com/reel/XXXXX" --verbose
```

従来どおり `--url` / `--input-file` も使えます。

## フェーズごとの確認目安

- Phase 1: HeyGen の設定が未投入でも `script.txt` までは生成されます。
- Phase 2-3: `HEYGEN_API_KEY` と `HEYGEN_AVATAR_ID` を設定すると `avatar_video.mp4` と `subtitle.srt` まで進みます。
- Phase 4-5: CapCutAPI をセットアップし、`CAPCUT_DRAFT_FOLDER` を設定すると CapCut Desktop 用ドラフト生成とコピーまで進みます。
- Phase 6-7: `config/instagram_cookies.txt` を置くと `--url` フローが使えます。

## CapCutAPI

このリポジトリでは `external/CapCutAPI/` を自動同梱していません。次のスクリプトを実行すると `external/CapCutAPI/` へ clone してセットアップします。

```bash
bash scripts/setup_capcut_api.sh
```

サーバー起動:

```bash
bash scripts/start_capcut_server.sh
```

疎通確認:

```bash
curl http://localhost:9000/create_draft \
  -X POST \
  -H "Content-Type: application/json" \
  -d '{"width":1080,"height":1920}'
```

`.env` の CapCut 関連はこの 2 つを入れてください。

```env
CAPCUT_API_WORKDIR=./external/CapCutAPI
CAPCUT_DRAFT_FOLDER=/Users/<YOUR_NAME>/Movies/CapCut/User Data/Projects/com.lveditor.draft
CAPCUT_API_URL=http://localhost:9000
```

## 出力

各実行ごとに `outputs/{timestamp}_{job_id}/` が作成されます。

- `source_video.mp4`
- `script.txt`
- `avatar_video_raw.mp4`
- `avatar_video.mp4`
- `avatar_subtitles.srt`
- `capcut_project/`
- `metadata.json`

## 注意事項

- API キーや Instagram クッキーは絶対にコミットしないでください。
- `config/instagram_cookies.txt` は `chmod 600` を推奨します。
- ログと `metadata.json` に秘密情報は出力しない実装にしています。
- CapCut 連携はブラウザ版ではなく、デスクトップ版 CapCut 前提です。
