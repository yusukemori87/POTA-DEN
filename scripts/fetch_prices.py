#!/usr/bin/env python3
"""毎日の価格巡回スクリプト（GitHub Actions から実行）

取得元:
  1. 楽天市場 商品検索API  … 環境変数 RAKUTEN_APP_ID（必須）, RAKUTEN_AFFILIATE_ID（任意）
  2. 価格.com 最安価格      … スクレイピング（1機種ごとに待機。失敗しても続行）
  3. Amazon PA-API          … 環境変数 PAAPI_ACCESS_KEY / PAAPI_SECRET_KEY / PAAPI_PARTNER_TAG が
                              揃っている場合のみ（アソシエイト承認後に有効化）

出力:
  data/prices/YYYY-MM-DD.json   その日のスナップショット
  data/price_history.json       機種ID → [{d, amazon, rakuten, kakaku}] の履歴（直近400日）
  data/products.json            各機種の prices フィールドを更新（現在価格・最安履歴）
"""
import json, os, re, sys, time, datetime, urllib.parse, urllib.request, html

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, 'data')
JST = datetime.timezone(datetime.timedelta(hours=9))
TODAY = datetime.datetime.now(JST).strftime('%Y-%m-%d')
UA = 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0 Safari/537.36'

EXCLUDE = re.compile(r'セット|パネル|拡張バッテリー|専用バッテリー|バッグ|ケース|カバー|ケーブル|アダプタ|充電器|収納|保護|中古|整備済|リファービッシュ|レンタル')

def get(url, headers=None, timeout=25):
    req = urllib.request.Request(url, headers={'User-Agent': UA, **(headers or {})})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode('utf-8', 'ignore')

def query_of(p):
    m = re.sub(r'\(.*?\)', '', p['model']).strip()
    m = re.sub(r'^(Jackery ポータブル電源|Jackery|Anker Solix|Anker|EcoFlow|BLUETTI|Dabbsson|ALLPOWERS|Victor|JVC|KENWOOD|Zendure)\s+', '', m).strip()
    return f"{p['brand']} {m}", m

def tokens_of(model):
    return [t.lower() for t in re.split(r'[\s/]+', model) if t and t not in ('ポータブル電源', '-')]

def title_matches(title, brand, toks):
    t = title.lower().replace(' ', '').replace('　', '')
    b = brand.lower().replace('ケンウッド', '')
    if b not in t and not (brand == 'JVCケンウッド' and ('jvc' in t or 'victor' in t or 'kenwood' in t)):
        return False
    full = ''.join(toks).replace(' ', '')
    if full not in t:
        return False
    if EXCLUDE.search(title):
        return False
    return True

# ---------- 楽天 ----------
def rakuten_price(p, app_id, aff_id):
    q, model = query_of(p)
    toks = tokens_of(model)
    params = {'applicationId': app_id, 'keyword': q + ' ポータブル電源', 'hits': 30, 'sort': '+itemPrice', 'formatVersion': 2, 'genreId': 0}
    if aff_id:
        params['affiliateId'] = aff_id
    url = 'https://app.rakuten.co.jp/services/api/IchibaItem/Search/20220601?' + urllib.parse.urlencode(params)
    try:
        js = json.loads(get(url))
    except Exception as e:
        return None, None, f'rakuten error: {e}'
    best = None
    for it in js.get('Items', []):
        name = it.get('itemName', '')
        price = it.get('itemPrice')
        if not price or price < (p.get('capacity_wh') or 0) * 15:  # 明らかに安すぎる（付属品等）は除外
            continue
        if not title_matches(name, p['brand'], toks):
            continue
        if best is None or price < best[0]:
            best = (price, it.get('affiliateUrl') or it.get('itemUrl'))
    if best:
        return best[0], best[1], 'ok'
    return None, None, 'no match'

# ---------- 価格.com ----------
def kakaku_price(p):
    q, model = query_of(p)
    toks = tokens_of(model)
    url = 'https://kakaku.com/search_results/' + urllib.parse.quote(q) + '/?category=0032'
    try:
        body = get(url)
    except Exception as e:
        return None, None, f'kakaku error: {e}'
    # 検索結果の各アイテム: タイトルと最安価格
    best = None
    for m in re.finditer(r'<a[^>]+href="(https://kakaku\.com/item/[^"]+)"[^>]*>([^<]{5,120})</a>[\s\S]{0,1500}?([\d,]{4,9})\s*円', body):
        href, title, price = m.group(1), html.unescape(m.group(2)), int(m.group(3).replace(',', ''))
        if not title_matches(title, p['brand'], toks):
            continue
        if price < (p.get('capacity_wh') or 0) * 15:
            continue
        if best is None or price < best[0]:
            best = (price, href)
    if best:
        return best[0], best[1], 'ok'
    return None, None, 'no match'

# ---------- Amazon PA-API（任意） ----------
def amazon_prices(products):
    keys = [os.environ.get(k) for k in ('PAAPI_ACCESS_KEY', 'PAAPI_SECRET_KEY', 'PAAPI_PARTNER_TAG')]
    if not all(keys):
        return {}
    try:
        from paapi5_python_sdk.api.default_api import DefaultApi
        from paapi5_python_sdk.get_items_request import GetItemsRequest
        from paapi5_python_sdk.get_items_resource import GetItemsResource
        from paapi5_python_sdk.partner_type import PartnerType
    except ImportError:
        print('paapi5_python_sdk 未インストール: pip install paapi5-python-sdk', file=sys.stderr)
        return {}
    api = DefaultApi(access_key=keys[0], secret_key=keys[1], host='webservices.amazon.co.jp', region='us-west-2')
    out = {}
    asins = [(i, p['amazon_asin']) for i, p in enumerate(products) if p.get('amazon_asin')]
    for k in range(0, len(asins), 10):
        chunk = asins[k:k + 10]
        req = GetItemsRequest(partner_tag=keys[2], partner_type=PartnerType.ASSOCIATES, marketplace='www.amazon.co.jp',
                              item_ids=[a for _, a in chunk], resources=[GetItemsResource.OFFERS_LISTINGS_PRICE, GetItemsResource.CUSTOMERREVIEWS_STARRATING, GetItemsResource.CUSTOMERREVIEWS_COUNT])
        try:
            res = api.get_items(req)
            for item in (res.items_result.items or []):
                try:
                    price = int(item.offers.listings[0].price.amount)
                    out[item.asin] = price
                except Exception:
                    pass
        except Exception as e:
            print('PA-API error', e, file=sys.stderr)
        time.sleep(1.1)
    return out

def main():
    products = json.load(open(os.path.join(DATA, 'products.json'), encoding='utf-8'))
    hist_path = os.path.join(DATA, 'price_history.json')
    history = json.load(open(hist_path, encoding='utf-8')) if os.path.exists(hist_path) else {}
    app_id = os.environ.get('RAKUTEN_APP_ID')
    aff_id = os.environ.get('RAKUTEN_AFFILIATE_ID', '')
    if not app_id:
        print('RAKUTEN_APP_ID が未設定です（楽天価格はスキップ）', file=sys.stderr)
    amz = amazon_prices(products)
    snap = {}
    limit = int(os.environ.get('LIMIT', '0') or 0)  # テスト用: 先頭N件だけ
    for i, p in enumerate(products):
        if limit and i >= limit:
            break
        rec = {'d': TODAY}
        if app_id:
            price, url, st = rakuten_price(p, app_id, aff_id)
            rec['rakuten'] = price
            if url:
                rec['rakuten_url'] = url
            time.sleep(0.4)
        kp, ku, kst = kakaku_price(p)
        rec['kakaku'] = kp
        if ku:
            rec['kakaku_url'] = ku
        if p.get('amazon_asin') in amz:
            rec['amazon'] = amz[p['amazon_asin']]
        snap[str(i)] = rec
        h = history.setdefault(str(i), [])
        h = [x for x in h if x.get('d') != TODAY]
        h.append({k: rec.get(k) for k in ('d', 'amazon', 'rakuten', 'kakaku')})
        history[str(i)] = h[-400:]
        # products.json の prices を更新
        cur = {k: rec.get(k) for k in ('amazon', 'rakuten', 'kakaku') if rec.get(k)}
        if 'amazon' not in cur and p.get('amazon_price'):
            cur['amazon'] = p['amazon_price']  # PA-API 未設定時は最後に手動取得した値を保持
        vals = [v for v in cur.values() if v]
        hist_vals = [x[k] for x in history[str(i)] for k in ('amazon', 'rakuten', 'kakaku') if x.get(k)]
        p['prices'] = {
            'updated': TODAY,
            'amazon': cur.get('amazon'), 'rakuten': cur.get('rakuten'), 'kakaku': cur.get('kakaku'),
            'rakuten_url': rec.get('rakuten_url'), 'kakaku_url': rec.get('kakaku_url'),
            'min': min(vals) if vals else None,
            'hist_min': min(hist_vals) if hist_vals else None,
            'history': [[x['d'], min([x[k] for k in ('amazon', 'rakuten', 'kakaku') if x.get(k)] or [None])] for x in history[str(i)][-90:]],
        }
        print(f"{i:3d} {p['brand']} {p['model'][:24]:24s} 楽天:{rec.get('rakuten')} 価格.com:{rec.get('kakaku')} Amazon:{rec.get('amazon')}", flush=True)
        time.sleep(1.0)
    os.makedirs(os.path.join(DATA, 'prices'), exist_ok=True)
    json.dump(snap, open(os.path.join(DATA, 'prices', TODAY + '.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    json.dump(history, open(hist_path, 'w', encoding='utf-8'), ensure_ascii=False)
    json.dump(products, open(os.path.join(DATA, 'products.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    print('done', TODAY)

if __name__ == '__main__':
    main()
