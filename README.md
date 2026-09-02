# ポタ電カタログ — 日次価格巡回＋自動公開

日本で買えるポータブル電源182機種の比較サイト。GitHub Actions が毎朝06:00(JST)に価格を巡回し、`docs/index.html` を再生成して GitHub Pages に公開します。

## 構成
- `data/products.json` … 全機種のマスターデータ（仕様・保証・セール最安値・レビュー要約・天の声・`prices`）
- `data/images.json` … 商品写真（dataURL）
- `data/price_history.json` … 機種ごとの価格履歴（自動生成）
- `data/prices/YYYY-MM-DD.json` … 日次スナップショット（自動生成）
- `scripts/fetch_prices.py` … 楽天市場API・価格.com・（任意）Amazon PA-API から価格取得
- `scripts/build.py` … `template.html` + データ → `docs/index.html`（一覧・SPA）と `docs/p/<slug>/index.html`（機種ごとの独立ページ182枚）、`sitemap.xml`、`robots.txt`
  - 独立ページは静的HTMLとして書き出すのでSEOに有効。JSON-LD（Product / AggregateRating / Review / BreadcrumbList）、canonical、OGP付き
  - 一覧の「詳細を見る」は実URLの `<a>`。クリックはモーダル＋History APIでURLだけ書き換わり、新規タブ・共有・検索流入では独立ページが開く
  - `docs/` は `.gitignore` 済み（毎日再生成してPagesに直接デプロイするため、リポジトリを肥大させない）
- `.github/workflows/daily.yml` … 毎日 21:00 UTC (= 06:00 JST) に実行、`data/`と`docs/`をコミットして Pages にデプロイ

## 必要な設定（GitHub の Settings → Secrets and variables → Actions）
| Secret | 必須 | 取得先 |
|---|---|---|
| `RAKUTEN_APP_ID` | 必須 | https://webservice.rakuten.co.jp/ でアプリ登録 → applicationId |
| `RAKUTEN_AFFILIATE_ID` | 任意 | 楽天アフィリエイトID（設定すると楽天リンクが成果報酬リンクになる） |
| `PAAPI_ACCESS_KEY` / `PAAPI_SECRET_KEY` / `PAAPI_PARTNER_TAG` | 任意 | Amazonアソシエイト承認後、PA-API 5.0 の認証情報。3つ揃うとAmazon価格も毎日更新 |

### 独自ドメインを使う場合（Variables、Secretsではない）
Settings → Secrets and variables → Actions → **Variables** タブ → New repository variable

| Variable | 値 | 効果 |
|---|---|---|
| `SITE_DOMAIN` | `example.com`（`https://`もスラッシュも付けない） | `docs/CNAME` を自動生成し、canonical・OGP・sitemap・パンくずのURLをこのドメインに切り替える |

未設定なら GitHub Pages の既定URL（`https://<user>.github.io/potaden-site/`）が使われる。

## 手動実行
Actions タブ → `daily-price-crawl` → `Run workflow`。

## ローカルで試す
```
RAKUTEN_APP_ID=xxxx LIMIT=5 python3 scripts/fetch_prices.py   # 先頭5機種だけ
SITE_URL=https://<あなたのID>.github.io/potaden-site python3 scripts/build.py && open docs/index.html
```

## データ更新のルール
- 仕様・レビュー要約・天の声は `data/products.json` を直接編集（`prices` は自動で上書きされる）
- 表示価格 = `prices.min`（Amazon / 楽天 / 価格.com の最安）。無ければ Amazon手動取得値 → 公式価格の順
- 「セール最安値」= 手動調査の `sale_low_price` と価格履歴の最安 `prices.hist_min` の小さい方
