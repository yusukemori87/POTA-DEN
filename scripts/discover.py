#!/usr/bin/env python3
"""新機種の自動収録（週1回・GitHub Actions から実行）

楽天市場APIをブランドごとに検索し、カタログに無い型番を見つけたら
**スペックだけ**を拾って products.json に追加する。天の声の採点はしない
（provisional: true が立っている機種はサイト上で「評価準備中」と表示される）。

誤収録を避けるためのガード:
  - 既知ブランドのみ（未知ブランドは candidates.json に記録するだけ）
  - 型番に数字を含むこと
  - 容量(Wh)が本文から読めること
  - 価格が下限以上
  - 異なる2店舗以上で同じ型番が出ていること
  - 1回の実行で追加するのは最大 MAX_ADD 件

出力:
  data/products.json    新機種を追記（provisional: true）
  data/candidates.json  今回見つけた候補と、採用/不採用の理由
"""
import json, os, re, sys, time, datetime, urllib.parse, urllib.request, urllib.error, html

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, 'data')
JST = datetime.timezone(datetime.timedelta(hours=9))
TODAY = datetime.datetime.now(JST).strftime('%Y-%m-%d')
UA = 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0 Safari/537.36'
EP = 'https://openapi.rakuten.co.jp/ichibams/api/IchibaItem/Search/20260701'
REFERER = (os.environ.get('RAKUTEN_REFERER') or
           (('https://' + os.environ['SITE_DOMAIN'].strip().replace('https://', '').strip('/') + '/')
            if os.environ.get('SITE_DOMAIN') else ''))
MAX_ADD = int(os.environ.get('MAX_ADD', '8'))
MIN_PRICE = int(os.environ.get('MIN_NEW_PRICE', '15000'))
MIN_SHOPS = 2

NOISE = re.compile(r'【[^】]*】|\([^)]*\)|（[^）]*）|ポータブル電源|大容量|防災|車中泊|キャンプ|アウトドア|セット|パネル|ソーラー|送料無料|正規品|公式|新品|限定|クーポン|ポイント|即納|あす楽|保証|付き|バッテリー|電源|災害|非常用|蓄電池|発電機')
EXCLUDE = re.compile(r'中古|整備済|リファービッシュ|レンタル|ケース|カバー|ケーブル|アダプタ|収納|保護フィルム|延長')

def get(url, timeout=10):
    h = {'User-Agent': UA}
    if REFERER:
        h['Referer'] = REFERER
        h['Origin'] = REFERER.rstrip('/')
    with urllib.request.urlopen(urllib.request.Request(url, headers=h), timeout=timeout) as r:
        return r.read().decode('utf-8', 'ignore')

def search(keyword, app_id, access_key, hits=30):
    params = {'applicationId': app_id, 'keyword': keyword, 'hits': hits,
              'formatVersion': 2, 'sort': 'standard'}
    if access_key:
        params['accessKey'] = access_key
    for attempt in range(3):
        try:
            return json.loads(get(EP + '?' + urllib.parse.urlencode(params))).get('Items', [])
        except urllib.error.HTTPError as e:
            if e.code == 429:
                time.sleep(2 + attempt * 2)
                continue
            print(f'  検索失敗 {keyword}: {e}', file=sys.stderr)
            return []
        except Exception as e:
            print(f'  検索失敗 {keyword}: {e}', file=sys.stderr)
            return []
    return []

def norm(s):
    return re.sub(r'[\s\-_]', '', (s or '')).lower()

def model_of(title, brand):
    t = html.unescape(title)
    t = NOISE.sub(' ', t)
    # ブランド名（表記ゆれ込み）を落とす
    for b in {brand, brand.replace(' ', ''), brand.lower()}:
        t = re.sub(re.escape(b), ' ', t, flags=re.I)
    toks = [x for x in re.split(r'[\s/,、。｜|]+', t) if x]
    UNIT = re.compile(r'^\d+(?:\.\d+)?(?:wh|w|v|a|ah|mah|kg|kwh|個|台|年)$', re.I)
    ENG = re.compile(r'^(portable|power|station|powerstation|solar|panel|generator|battery|japan|official|store|model|type|for|with|and|the)$', re.I)
    SKU = re.compile(r'^\d{6,}$')
    keep = []
    for x in toks:
        if UNIT.match(x) or ENG.match(x) or SKU.match(x):
            continue
        if re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9\-+.]{0,15}', x):
            keep.append(x)
        if len(keep) >= 4:
            break
    if not keep or not any(re.search(r'\d', x) for x in keep):
        return None
    m = ' '.join(keep)
    return m if 2 <= len(m) <= 28 else None

def wh_of(*texts):
    for t in texts:
        if not t:
            continue
        for m in re.finditer(r'(\d{3,6})\s*(?:wh|Wh|WH|ワットアワー)', t):
            v = int(m.group(1))
            if 100 <= v <= 30000:
                return v
    return None

def watt_of(*texts):
    for t in texts:
        if not t:
            continue
        for m in re.finditer(r'(?:定格|出力|AC出力)\D{0,6}(\d{3,5})\s*W', t):
            v = int(m.group(1))
            if 100 <= v <= 8000:
                return v
    return None

def main():
    app_id = os.environ.get('RAKUTEN_APP_ID')
    access_key = os.environ.get('RAKUTEN_ACCESS_KEY', '')
    if not app_id:
        print('RAKUTEN_APP_ID が未設定のため中止', file=sys.stderr)
        return
    products = json.load(open(os.path.join(DATA, 'products.json'), encoding='utf-8'))
    brands = sorted({p['brand'] for p in products})
    known = set()
    for p in products:
        known.add(norm(p['brand']) + '|' + norm(re.sub(r'\(.*?\)', '', p['model'])))
    known_models_by_brand = {}
    for p in products:
        known_models_by_brand.setdefault(norm(p['brand']), []).append(
            norm(re.sub(r'\(.*?\)', '', p['model'])))

    def digit_tokens(model):
        return {t.lower() for t in re.split(r'[^A-Za-z0-9]+', model or '') if t and re.search(r'\d', t)}

    # ブランド＋容量＋数字トークンが一致する既存機種があれば同一とみなす
    by_brand_cap = {}
    for p in products:
        if p.get('capacity_wh'):
            by_brand_cap.setdefault((norm(p['brand']), p['capacity_wh']), []).append(digit_tokens(p['model']))

    def is_known(brand, model, cap):
        nm = norm(model)
        if norm(brand) + '|' + nm in known:
            return True
        for km in known_models_by_brand.get(norm(brand), []):
            if nm and km and (nm in km or km in nm):
                return True
        if cap:
            mine = digit_tokens(model)
            for toks in by_brand_cap.get((norm(brand), cap), []):
                if mine & toks:
                    return True
        return False

    # 過去に自動収録した仮エントリのうち、正規エントリと重複しているものを掃除する
    curated = [p for p in products if not p.get('provisional')]
    removed = []
    for p in list(products):
        if not p.get('provisional'):
            continue
        for c in curated:
            if norm(c['brand']) == norm(p['brand']) and c.get('capacity_wh') and c['capacity_wh'] == p.get('capacity_wh') \
               and (digit_tokens(c['model']) & digit_tokens(p['model'])):
                products.remove(p)
                removed.append(f"{p['brand']} {p['model']}")
                break
    if removed:
        print('重複していた自動収録エントリを削除: ' + ' / '.join(removed))

    found = {}   # key -> dict
    for b in brands:
        items = search(f'{b} ポータブル電源', app_id, access_key)
        for it in items:
            name = it.get('itemName', '')
            if EXCLUDE.search(name):
                continue
            price = it.get('itemPrice') or 0
            if price < MIN_PRICE:
                continue
            if norm(b) not in norm(name):
                continue
            m = model_of(name, b)
            if not m:
                continue
            key = norm(b) + '|' + norm(m)
            # 既存カタログに含まれる（部分一致も既存扱い）
            cap = wh_of(name, it.get('itemCaption'))
            if is_known(b, m, cap):
                continue
            e = found.setdefault(key, {'brand': b, 'model': m, 'shops': set(), 'prices': [],
                                       'cap': None, 'watt': None, 'url': None, 'image': None,
                                       'titles': []})
            e['shops'].add(it.get('shopCode') or it.get('shopName'))
            e['prices'].append(price)
            e['titles'].append(name[:80])
            e['cap'] = e['cap'] or cap
            e['watt'] = e['watt'] or watt_of(name, it.get('itemCaption'))
            if not e['url']:
                e['url'] = it.get('affiliateUrl') or it.get('itemUrl')
            if not e['image']:
                imgs = it.get('mediumImageUrls') or []
                im = imgs[0] if imgs else None
                if isinstance(im, dict):
                    im = im.get('imageUrl')
                if im:
                    e['image'] = re.sub(r'\?.*$', '', im).replace('http://', 'https://')
        time.sleep(1.0)

    report, added = [], 0
    for key, e in sorted(found.items(), key=lambda kv: -len(kv[1]['shops'])):
        why = None
        if len(e['shops']) < MIN_SHOPS:
            why = f'出品店舗が{len(e["shops"])}店のみ（{MIN_SHOPS}店以上必要）'
        elif not e['cap']:
            why = '容量(Wh)が読み取れない'
        elif added >= MAX_ADD:
            why = '今回の追加上限に達した（次回に持ち越し）'
        report.append({'brand': e['brand'], 'model': e['model'], 'capacity_wh': e['cap'],
                       'price': min(e['prices']), 'shops': len(e['shops']),
                       'adopted': why is None, 'reason': why or '追加した',
                       'sample_title': e['titles'][0]})
        if why:
            continue
        products.append({
            'brand': e['brand'], 'model': e['model'], 'capacity_wh': e['cap'],
            'rated_output_w': e['watt'], 'surge_output_w': None, 'solar_input_w': None,
            'ac_input_w': None, 'battery': None, 'cycles': None, 'weight_kg': None,
            'expandable': False, 'max_expand_wh': None, 'ups_ms': None,
            'price_jpy': min(e['prices']), 'rating': None, 'reviews': None,
            'release_year': int(TODAY[:4]), 'official_url': None,
            'notes': f'{TODAY} に楽天市場の出品から自動収録。スペックは販売ページ記載の範囲のみ。',
            'amazon_price': None, 'amazon_asin': None,
            'warranty_years': None, 'warranty_ext_years': None, 'warranty_note': None,
            'sale_low_price': None, 'sale_low_note': None,
            'review': None, 'tenno': None, 'v200': False, 'v200_note': None,
            'years_on_market': 0,
            'provisional': True, 'discovered': TODAY,
            'prices': {'updated': TODAY, 'rakuten': min(e['prices']), 'min': min(e['prices']),
                       'rakuten_url': e['url'], 'image': e['image']},
        })
        added += 1
        print(f'追加: {e["brand"]} {e["model"]} / {e["cap"]}Wh / ¥{min(e["prices"]):,}')

    json.dump(products, open(os.path.join(DATA, 'products.json'), 'w', encoding='utf-8'),
              ensure_ascii=False, indent=1)
    json.dump({'date': TODAY, 'candidates': report, 'added': added, 'removed_duplicates': removed},
              open(os.path.join(DATA, 'candidates.json'), 'w', encoding='utf-8'),
              ensure_ascii=False, indent=1)
    print(f'---- 新機種スキャン {TODAY} ----')
    print(f'  候補 {len(report)} 件 / 追加 {added} 件 → data/candidates.json')

if __name__ == '__main__':
    main()
