# yasero.dev

このリポジトリは `public/` 配下の静的ファイルを GitHub Pages にデプロイする構成です。

## GitHub Pages の有効化
1. GitHub リポジトリの `Settings` -> `Pages` を開く
2. `Build and deployment` の `Source` を `GitHub Actions` に設定
3. `main` または `master` ブランチへ push すると `.github/workflows/deploy-pages.yml` が実行され、`public/` が公開される

## eufy 体重表示の設定
MyFitnessPal の代わりに、GitHub Actions が eufy の非公開 API から最新体重を取得して `public/data/weight.json` を更新し、`index.html` で表示します。

1. `Settings` -> `Secrets and variables` -> `Actions` で下記 Secrets を登録
2. `EUFY_EMAIL`: eufy ログインメールアドレス
3. `EUFY_PASSWORD`: eufy ログインパスワード
4. `EUFY_CLIENT_ID`: eufy API の client id（必須）
5. `EUFY_CLIENT_SECRET`: eufy API の client secret（必須）
6. `EUFY_DEVICE_ID` (任意): 対象の体重計デバイスIDを固定したい場合に指定
7. (任意) `Repository variables` に `EUFY_PREVIOUS_WEIGHT_URL` を設定
8. (任意) `Repository variables` に `TARGET_WEIGHT_KG` を設定（未設定時は `55.0`）
9. `Actions` の `Deploy static site to GitHub Pages` を手動実行 (`workflow_dispatch`) して動作確認

補足:
- ワークフローは 24 時間ごとに定期実行されます（UTC 00:15）。
- 取得前に公開中 `weight.json` を復元するため、取得失敗時は前回成功値を維持できます。
- API 仕様変更が起きる可能性があるため、失敗時は Actions ログを確認してください。

## #yasero_dev 投稿URLの運用（Git履歴を増やさない）
`#yasero_dev` の投稿URLは `public/data/yasero_dev_posts.json` をGitで直接更新せず、Repository Variable で管理します。

1. `Settings` -> `Secrets and variables` -> `Actions` -> `Variables` で `YASERO_POST_URLS` を作成（初期値 `[]`）
2. `Actions` の `Add #yasero_dev post URL` を手動実行し、`post_url` に `https://x.com/.../status/...` を入力
3. デプロイ時に `YASERO_POST_URLS` から `public/data/yasero_dev_posts.json` を生成して公開

補足:
- `Add #yasero_dev post URL` は URL 重複を自動除去し、新しいURLを先頭に追加します。
- `twitter.com` URLを入力した場合も、保存時に `x.com` 形式へ正規化されます。
