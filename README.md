# yasero.dev

このリポジトリは `public/` 配下の静的ファイルを GitHub Pages にデプロイする構成です。

## GitHub Pages の有効化
1. GitHub リポジトリの `Settings` -> `Pages` を開く
2. `Build and deployment` の `Source` を `GitHub Actions` に設定
3. `main` または `master` ブランチへ push すると `.github/workflows/deploy-pages.yml` が実行され、`public/` が公開される
