#!/usr/bin/env python3
"""data/products.json + data/images.json + template.html から
   docs/index.html（一覧・SPA）と docs/p/<slug>/index.html（機種ごとの独立ページ）を生成。
   独立ページはサーバー側でHTMLを書き出す静的ページなので、検索エンジンにそのままインデックスされる。"""
import json, os, re, html, datetime, urllib.parse

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DOMAIN = (os.environ.get('SITE_DOMAIN') or '').strip().replace('https://', '').replace('http://', '').strip('/')
SITE = ('https://' + DOMAIN) if DOMAIN else (os.environ.get('SITE_URL') or 'https://example.github.io/potaden-site').rstrip('/')
FAVICON = ("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32'%3E"
           "%3Crect width='32' height='32' rx='8' fill='%230E7C66'/%3E"
           "%3Crect x='10.75' y='7.75' width='10.5' height='16.5' rx='2.5' fill='none' stroke='%23fff' stroke-width='2.5'/%3E"
           "%3Crect x='12.5' y='17' width='7' height='5.5' rx='1' fill='%23fff'/%3E%3C/svg%3E")
ICONS = (f'<link rel="icon" href="{FAVICON}">'
         f'<link rel="apple-touch-icon" href="{FAVICON}">')
JST = datetime.timezone(datetime.timedelta(hours=9))
TODAY = datetime.datetime.now(JST).strftime('%Y-%m-%d')
AMAZON_TAG = os.environ.get('AMAZON_TAG', 'poonyan87-22')  # AmazonアソシエイトのトラッキングID
RAKUTEN_AFL = os.environ.get('RAKUTEN_AFL', 'https://hb.afl.rakuten.co.jp/ichiba/57142585.1577c0d6.57142586.3a6608f9/?pc=')

d = json.load(open(os.path.join(ROOT, 'data', 'products.json'), encoding='utf-8'))
IMG = json.load(open(os.path.join(ROOT, 'data', 'images.json'), encoding='utf-8'))
KEYS = ['brand','model','capacity_wh','rated_output_w','surge_output_w','solar_input_w','ac_input_w','battery','cycles',
        'weight_kg','expandable','max_expand_wh','ups_ms','price_jpy','rating','reviews','release_year','official_url',
        'notes','amazon_price','amazon_asin','warranty_years','warranty_ext_years','warranty_note','sale_low_price',
        'sale_low_note','review','tenno','prices','v200','v200_note','years_on_market',
        'discontinued','provisional','discovered']

def clean_model(m):
    m = re.sub(r'\s+', ' ', m).strip()
    return re.sub(r'^(Jackery ポータブル電源|Jackery|Anker Solix|Anker|EcoFlow|BLUETTI|Dabbsson|ALLPOWERS|Victor|JVC|KENWOOD|Zendure)\s+', '', m).strip()

def full_name(brand, model):
    """表示・URL用の正式名。model が既にブランド名で始まる場合はブランドを重ねない
       （例: DJI + 'DJI Power 1000' → 'DJI Power 1000'、'DJI DJI Power 1000' にしない）"""
    return model if model.lower().startswith(brand.lower()) else f'{brand} {model}'

def slug(brand, model):
    s = full_name(brand, model).lower()
    s = re.sub(r'\(.*?\)', '', s)
    s = re.sub(r'[^a-z0-9ぁ-んァ-ヶ一-龠]+', '-', s)
    return s.strip('-')

prods = []
for p in d:
    q = {k: p.get(k) for k in KEYS}
    q['model'] = clean_model(q['model'])
    prods.append(q)

OG_IMAGE = f'{SITE}/ogp.png'

# ---------- 一覧ページ ----------
tpl = open(os.path.join(ROOT, 'template.html'), encoding='utf-8').read()
def wrap(body, head_extra=''):
    head, rest = body.split('<style>', 1)
    return ('<!doctype html><html lang="ja"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width,initial-scale=1">' + head + head_extra +
            '<style>' + rest.replace('</style>', '</style></head><body>', 1) + '</body></html>')

index_html = tpl.replace('__DATA__', json.dumps(prods, ensure_ascii=False, separators=(',', ':'))) \
                .replace('__IMG__', json.dumps(IMG, separators=(',', ':')))
N = len(prods)
index_html = index_html.replace('__N__', str(N))
SITE_NAME = 'ポタ電カタログ'
INDEX_TITLE = f'ポータブル電源 比較{N}機種｜Wh単価・保証・辛口レビュー｜{SITE_NAME}'
INDEX_DESC = (f'日本で買えるポータブル電源{N}機種を横断比較。容量・Wh単価・メーカー保証・セール時最安値を一覧で並べ、'
              'レビューを読み込んだ編集部の辛口採点（100点満点）つき。価格は毎日自動更新。')
ld_site = {"@context": "https://schema.org", "@type": "WebSite", "name": SITE_NAME, "url": SITE + '/',
           "description": INDEX_DESC, "inLanguage": "ja",
           "publisher": {"@type": "Organization", "name": SITE_NAME, "url": SITE + '/'}}
_top = sorted(prods, key=lambda x: -((x.get('tenno') or {}).get('score') or 0))[:20]
ld_list = {"@context": "https://schema.org", "@type": "ItemList",
           "name": f'ポータブル電源 総合評価ランキング（全{N}機種）', "numberOfItems": len(_top),
           "itemListElement": [{"@type": "ListItem", "position": i + 1,
                                "name": full_name(q['brand'], q['model']),
                                "url": f"{SITE}/p/{slug(q['brand'], q['model'])}/"}
                               for i, q in enumerate(_top)]}
index_head = (f'<link rel="canonical" href="{SITE}/">{ICONS}'
              f'<meta property="og:type" content="website">'
              f'<meta property="og:site_name" content="{SITE_NAME}">'
              f'<meta property="og:title" content="{html.escape(INDEX_TITLE, quote=True)}">'
              f'<meta property="og:description" content="{html.escape(INDEX_DESC, quote=True)}">'
              f'<meta property="og:url" content="{SITE}/">'
              f'<meta property="og:image" content="{OG_IMAGE}">'
              f'<meta property="og:locale" content="ja_JP">'
              f'<meta name="twitter:card" content="summary_large_image">'
              f'<meta name="twitter:title" content="{html.escape(INDEX_TITLE, quote=True)}">'
              f'<meta name="twitter:description" content="{html.escape(INDEX_DESC, quote=True)}">'
              f'<meta name="twitter:image" content="{OG_IMAGE}">'
              f'<meta name="theme-color" content="#0E7C66">'
              f'<script type="application/ld+json">{json.dumps(ld_site, ensure_ascii=False)}</script>'
              f'<script type="application/ld+json">{json.dumps(ld_list, ensure_ascii=False)}</script>'
              '<script>window.POTADEN_PAGE_BASE="p/";</script>')
index_html = wrap(index_html, index_head)
os.makedirs(os.path.join(ROOT, 'docs'), exist_ok=True)
open(os.path.join(ROOT, 'docs', 'index.html'), 'w', encoding='utf-8').write(index_html)
open(os.path.join(ROOT, 'docs', '.nojekyll'), 'w').close()
import shutil
_ogp_src = os.path.join(ROOT, 'assets', 'ogp.png')
if os.path.exists(_ogp_src):
    shutil.copyfile(_ogp_src, os.path.join(ROOT, 'docs', 'ogp.png'))
if DOMAIN:  # 独自ドメイン用。GitHub Pages はこのファイルを見て配信先ドメインを決める
    open(os.path.join(ROOT, 'docs', 'CNAME'), 'w').write(DOMAIN + '\n')

# ---------- 機種ごとの独立ページ ----------
PAGE_CSS = re.search(r'<style>([\s\S]*?)</style>', tpl).group(1)
e = lambda s: html.escape(str(s if s is not None else ''), quote=True)
fmt = lambda n: '—' if n is None else f'{n:,}'
yen = lambda n: '—' if n is None else '¥' + f'{n:,}'

def stars_html(v):
    if v is None: return ''
    out = ''
    for i in range(1, 6):
        cls = 'f' if v >= i else ('h' if v >= i - 0.5 else '')
        out += f'<i class="{cls}"></i>'
    return f'<span class="stars">{out}</span>'

CRITDEF = ('<details class="crit-def"><summary>「致命的」「要注意」の判定基準</summary><div class="in">'
 '<div><h3><b class="c1">致命的</b>製品を選ぶ理由が消えるレベル</h3><ol>'
 '<li>発煙・発火・焦げ・異臭・溶損</li><li>バッテリーの膨張・液漏れ</li><li>使用中に突然停止する／出力が落ちる</li>'
 '<li>購入直後〜1年以内に充電できない・起動しない</li><li>1〜2年で完全故障（電源が入らない）</li>'
 '<li>交換品でも同じ症状が再発（個体差ではなく設計・製造の問題）</li>'
 '<li>保証期間内なのに修理拒否・サポート無応答・連絡が途絶える</li>'
 '<li>公称値との重大な乖離（実容量が明らかに少ない、定格出力が出ない、サイクル数の偽装）</li>'
 '<li>安全に関わる設計上の問題（ポートの焼損、ケース変形、アース不良）</li>'
 '<li>リコール・メーカーによる不具合告知</li></ol></div>'
 '<div><h3><b class="c2">要注意</b>致命傷ではないが知っておくべき</h3><ol>'
 '<li>単発の初期不良（交換対応で解決している）</li><li>ファームウェア更新後の不具合（修正済み・回避策あり）</li>'
 '<li>表示やアプリの不具合（残量表示のズレ、Bluetooth切断）</li><li>気になる程度の自然放電</li>'
 '<li>特定条件でのみ出る症状（高負荷時・低温時など）</li><li>3年以上使ってからの故障</li>'
 '<li>サポートの対応が遅い（最終的には解決している）</li></ol></div>'
 '<p>仕様への不満（重い・容量が小さい・価格が高い）、購入者側の環境の問題（自宅のブレーカーが落ちる等）、'
 '業界共通の挙動、配送・梱包の問題、根拠のない不安は<b>製品の落ち度ではない</b>ため掲載していません。</p>'
 '</div></details>')

def product_page(i, p):
    sl = slug(p['brand'], p['model'])
    url = f'{SITE}/p/{sl}/'
    pr = p.get('prices') or {}
    img = IMG.get(str(i)) or pr.get('image')
    cur = pr.get('min') or p.get('amazon_price') or p.get('price_jpy')
    lows = [x for x in [p.get('sale_low_price'), pr.get('hist_min'), cur] if x]
    low = min(lows) if lows else None
    ppw = round(cur / p['capacity_wh'], 1) if cur and p.get('capacity_wh') else None
    t = p.get('tenno') or {}
    rv = p.get('review') or {}
    FN = full_name(p['brand'], p['model'])
    title = f"{FN} のレビュー・評価と最安値｜ポタ電カタログ"
    desc = (f"{FN}（{fmt(p.get('capacity_wh'))}Wh／定格{fmt(p.get('rated_output_w'))}W）の"
            f"実売価格{yen(cur)}、Wh単価{ppw}円/Wh、保証{p.get('warranty_years')}年。"
            f"全レビュー要約と総合評価{t.get('score')}点の辛口採点。{t.get('verdict','')}")[:158]
    kv = [('容量', f"{fmt(p.get('capacity_wh'))} Wh"), ('定格出力', f"{fmt(p['rated_output_w'])} W" if p.get('rated_output_w') else 'DC専用'),
          ('瞬間最大出力', f"{fmt(p['surge_output_w'])} W" if p.get('surge_output_w') else '—'),
          ('ソーラー最大入力', f"{fmt(p['solar_input_w'])} W" if p.get('solar_input_w') else '—'),
          ('AC充電入力', f"{fmt(p['ac_input_w'])} W" if p.get('ac_input_w') else '—'), ('電池', p.get('battery') or '—'),
          ('サイクル寿命', f"{fmt(p['cycles'])} 回" if p.get('cycles') else '—'),
          ('重量', f"{p['weight_kg']} kg" if p.get('weight_kg') is not None else '—'),
          ('拡張', ('対応' + (f"（最大 {fmt(p['max_expand_wh'])} Wh）" if p.get('max_expand_wh') else '')) if p.get('expandable') else '非対応'),
          ('UPS切替', f"{p['ups_ms']} ms" if p.get('ups_ms') is not None else '—'),
          ('Wh単価', f"{ppw} 円/Wh" if ppw else '—'),
          ('メーカー保証', (f"{p['warranty_years']}年（登録で{p['warranty_ext_years']}年）"
                       if p.get('warranty_ext_years') and p['warranty_ext_years'] > p['warranty_years']
                       else f"{p['warranty_years']}年") if p.get('warranty_years') else '—'),
          ('200V出力', '対応' if p.get('v200') else '非対応'),
          ('セール時最安値', yen(low)),
          ('発売年', f"{p['release_year']}年（{p.get('years_on_market')}年目）" if p.get('release_year') else '—'),
          ('公式価格', yen(p.get('price_jpy'))), ('Amazon価格', yen(p.get('amazon_price')))]
    ld = {"@context": "https://schema.org", "@type": "Product", "name": FN,
          "brand": {"@type": "Brand", "name": p['brand']}, "url": url,
          "description": f"{fmt(p.get('capacity_wh'))}Wh のポータブル電源。定格{fmt(p.get('rated_output_w'))}W、ソーラー入力{fmt(p.get('solar_input_w'))}W、{p.get('battery') or ''}。"}
    if cur:
        ld["offers"] = {"@type": "Offer", "price": cur, "priceCurrency": "JPY", "availability": "https://schema.org/InStock", "url": url}
    if p.get('rating') and p.get('reviews'):
        ld["aggregateRating"] = {"@type": "AggregateRating", "ratingValue": p['rating'], "reviewCount": p['reviews']}
    if t.get('score'):
        ld["review"] = {"@type": "Review", "name": t.get('verdict'), "reviewBody": t.get('body'),
                        "author": {"@type": "Organization", "name": "ポタ電カタログ編集部"},
                        "reviewRating": {"@type": "Rating", "ratingValue": t['score'], "bestRating": 100, "worstRating": 0}}
    crumbs = {"@context": "https://schema.org", "@type": "BreadcrumbList", "itemListElement": [
        {"@type": "ListItem", "position": 1, "name": "ポタ電カタログ", "item": SITE + '/'},
        {"@type": "ListItem", "position": 2, "name": FN, "item": url}]}
    sc = t.get('score') or 0
    tn_cls = 's4' if sc >= 75 else 's3' if sc >= 60 else 's2' if sc >= 45 else 's1'
    amz = (f"https://www.amazon.co.jp/dp/{p['amazon_asin']}" if p.get('amazon_asin')
           else 'https://www.amazon.co.jp/s?k=' + re.sub(r'\s+', '+', f"{FN} ポータブル電源"))
    if AMAZON_TAG:
        amz += ('&' if '?' in amz else '?') + 'tag=' + AMAZON_TAG
    rak = pr.get('rakuten_url') or ('https://search.rakuten.co.jp/search/mall/' + re.sub(r'\s+', '%20', FN) + '/')
    if RAKUTEN_AFL and 'hb.afl.rakuten.co.jp' not in rak:   # 既に成果報酬リンクならそのまま
        rak = RAKUTEN_AFL + urllib.parse.quote(rak, safe='')
    body = f"""<div class="top"><div class="topin"><a class="logo" href="{SITE}/" style="text-decoration:none;color:inherit"><i></i>ポタ電カタログ<small>JAPAN</small></a></div></div>
<div class="page" style="grid-template-columns:1fr;max-width:1000px">
<main>
<nav style="font-size:12px;color:var(--muted);margin-bottom:10px"><a href="{SITE}/">ポタ電カタログ</a> ＞ {e(FN)}</nav>
<article class="modal" style="position:static;box-shadow:none;border:1px solid var(--line)">
<div class="mimg">{f'<img src="{img}" alt="{e(FN)} の製品画像" width="280" height="280">' if img else f'<div class="noimg"><b>{fmt(p.get("capacity_wh"))}</b>Wh</div>'}</div>
<div class="mbody">
<h1 style="margin:0;font-size:24px;line-height:1.25">{f'<span class="brand" style="display:block">{e(p["brand"])}</span>' if FN != p['model'] else ''}{e(p['model'])}</h1>
{f'<div class="rating">{stars_html(p["rating"])}<span class="rv">{p["rating"]}</span><span class="rc">({fmt(p.get("reviews"))}件)</span></div>' if p.get('rating') else '<div class="rating none">Amazon評価なし</div>'}
<div class="pricebox"><span class="price"><small>¥</small>{fmt(cur)}</span>{f'<span class="low"><span class="tag">セール最安</span><b>{yen(low)}</b></span>' if low and cur and low < cur else ''}</div>
<div class="kv">{''.join(f'<div><span>{e(k)}</span><b>{e(v)}</b></div>' for k, v in kv)}</div>
{f'<div class="notes">{e(p["notes"])}</div>' if p.get('notes') else ''}
<section class="msec"><h2 style="margin:0 0 6px;font-size:12px;letter-spacing:.08em;color:var(--muted);font-family:var(--mono)">総合評価 — 天の声（編集部の辛口採点）</h2>
<div class="tennobox"><div class="sc">{sc}<small>点</small></div><div class="vd">{e(t.get('verdict'))}</div><div class="bd">{e(t.get('body'))}</div>
<div class="ba"><span>{e(t.get('best_for'))}</span><span class="no">{e(t.get('avoid_if'))}</span></div><div class="bo">{('内訳: 基礎 ' + str(t.get('base_score')) + '点 ＋ 継続販売ボーナス ' + str(t.get('longevity_bonus')) + '点（' + e(t.get('longevity_note','')) + '）') if t.get('longevity_bonus') else e(t.get('longevity_note',''))}</div></div></section>
<section class="msec"><h2 style="margin:0 0 6px;font-size:12px;letter-spacing:.08em;color:var(--muted);font-family:var(--mono)">全レビューの要約</h2>
<p class="summ" style="margin:0 0 8px">{e(rv.get('summary'))}</p>
<div class="pc"><ul class="p">{''.join(f'<li>{e(x)}</li>' for x in rv.get('pros', []))}</ul><ul class="n">{''.join(f'<li>{e(x)}</li>' for x in rv.get('cons', []))}</ul></div></section>
<section class="msec"><h2 style="margin:0 0 6px;font-size:12px;letter-spacing:.08em;color:var(--muted);font-family:var(--mono)">天の声が気になったレビュー</h2>
{''.join(f'<div class="flag {"f1" if f["level"]=="致命的" else "f2"}"><b>{e(f["level"])}</b>{e(f["text"])}<small>{e(f["source"])}</small></div>' for f in rv.get('flagged', [])) or '<p class="rvs" style="margin:0">致命的・要注意に該当するレビューは確認できなかった。</p>'}{CRITDEF}</section>
{('<section class="msec"><h2 style="margin:0 0 6px;font-size:12px;letter-spacing:.08em;color:var(--muted);font-family:var(--mono)">Amazonレビュー抜粋（低評価・最新）</h2><div class="rvs">' + ''.join(f'<div><span class="st">★{s.get("s") or "-"}</span>{e(s.get("t"))}<span class="dt">{e(s.get("d"))}{"・購入済み" if s.get("v") else ""}</span><br>{e(s.get("b"))}</div>' for s in rv.get('amazon_samples', [])) + '</div></section>') if rv.get('amazon_samples') else ''}
<div class="macts"><a class="btn am" href="{e(amz)}" target="_blank" rel="nofollow noopener sponsored">Amazonで見る</a><a class="btn" href="{e(rak)}" target="_blank" rel="nofollow noopener sponsored">楽天で探す</a>{f'<a class="btn" href="{e(p["official_url"])}" target="_blank" rel="noopener">公式サイト</a>' if p.get('official_url') else ''}<a class="btn" href="{SITE}/">他の機種と比較する</a></div>
</div></article>
<footer style="padding:24px 0 40px;color:var(--ink2);font-size:12px;max-width:80ch">価格は{e(pr.get('updated') or TODAY)}時点。Amazon・楽天・価格.comの最安値を毎日自動取得しています。「総合評価（天の声）」は編集部がレビューを横断して読み、仕様・価格・保証・サポート報告を突き合わせて付けた独自の辛口採点です。本ページのリンクにはアフィリエイトリンクを含みます。<b>Amazonのアソシエイトとして、ポタ電カタログは適格販売により収入を得ています。</b>価格は取得時点のもので変動します。最新の価格・在庫は各販売ページでご確認ください。</footer>
</main></div>"""
    head = (f'<title>{e(title)}</title><meta name="description" content="{e(desc)}">'
            f'<link rel="canonical" href="{url}">'
            f'<meta property="og:type" content="product"><meta property="og:title" content="{e(title)}">'
            f'<meta property="og:description" content="{e(desc)}"><meta property="og:url" content="{url}">'
            f'<meta property="og:site_name" content="ポタ電カタログ"><meta property="og:locale" content="ja_JP">'
            f'<meta property="og:image" content="{OG_IMAGE}">'
            f'<meta name="twitter:card" content="summary_large_image">'
            f'<meta name="twitter:title" content="{e(title)}"><meta name="twitter:description" content="{e(desc)}">'
            f'<meta name="twitter:image" content="{OG_IMAGE}">'
            f'<meta name="theme-color" content="#0E7C66">{ICONS}'
            '<link rel="preconnect" href="https://fonts.googleapis.com">'
            '<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=IBM+Plex+Sans+JP:wght@400;500;600;700&family=IBM+Plex+Mono:wght@500;600&display=swap">'
            f'<script type="application/ld+json">{json.dumps(ld, ensure_ascii=False)}</script>'
            f'<script type="application/ld+json">{json.dumps(crumbs, ensure_ascii=False)}</script>'
            f'<style>{PAGE_CSS}</style>'
            '<style>article.modal{align-items:start}.mimg{align-self:start;place-items:start center;'
            'position:sticky;top:64px;min-height:0;padding:28px 24px}.mimg img{max-height:340px}'
            '@media(max-width:860px){.mimg{position:static}}.crit-def h3{margin:0 0 4px;font-size:12px;display:flex;align-items:center;gap:6px}</style>')
    return sl, f'<!doctype html><html lang="ja"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">{head}</head><body>{body}</body></html>'

urls = [f'{SITE}/']
for i, p in enumerate(prods):
    sl, page = product_page(i, p)
    dirp = os.path.join(ROOT, 'docs', 'p', sl)
    os.makedirs(dirp, exist_ok=True)
    open(os.path.join(dirp, 'index.html'), 'w', encoding='utf-8').write(page)
    urls.append(f'{SITE}/p/{sl}/')

open(os.path.join(ROOT, 'docs', 'sitemap.xml'), 'w', encoding='utf-8').write(
    '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n' +
    ''.join(f'<url><loc>{u}</loc><lastmod>{TODAY}</lastmod></url>\n' for u in urls) + '</urlset>\n')
open(os.path.join(ROOT, 'docs', 'robots.txt'), 'w', encoding='utf-8').write(
    f'User-agent: *\nAllow: /\nSitemap: {SITE}/sitemap.xml\n')

# ---------- 404 ----------
_404_body = (f'<div class="top"><div class="topin"><a class="logo" href="{SITE}/" style="text-decoration:none;color:inherit">'
             '<i></i>ポタ電カタログ<small>JAPAN</small></a></div></div>'
             '<div class="page" style="grid-template-columns:1fr;max-width:1000px"><main>'
             '<div class="lede" style="padding:40px 0"><h1>ページが見つかりません（404）</h1>'
             '<p>お探しのページは移動したか、掲載を終了した可能性があります。'
             '機種の掲載終了・URLの変更が原因のことが多いので、一覧から探し直してください。</p>'
             f'<p style="margin-top:16px"><a class="btn" href="{SITE}/" '
             'style="display:inline-block;padding:10px 18px;border:1px solid var(--line2);border-radius:8px;'
             'text-decoration:none;color:inherit">ポタ電カタログのトップへ</a></p></div>'
             '</main></div>')
open(os.path.join(ROOT, 'docs', '404.html'), 'w', encoding='utf-8').write(
    '<!doctype html><html lang="ja"><head><meta charset="utf-8">'
    '<meta name="viewport" content="width=device-width,initial-scale=1">'
    '<title>ページが見つかりません｜ポタ電カタログ</title><meta name="robots" content="noindex">'
    + ICONS +
    '<link rel="preconnect" href="https://fonts.googleapis.com">'
    '<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=IBM+Plex+Sans+JP:wght@400;500;600;700&family=IBM+Plex+Mono:wght@500;600&display=swap">'
    f'<style>{PAGE_CSS}</style></head><body>{_404_body}</body></html>')
print('SITE =', SITE)
print(f'{len(prods)} products → docs/index.html + docs/p/*/index.html ({len(urls)-1}ページ) + sitemap.xml')
