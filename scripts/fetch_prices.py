#!/usr/bin/env python3
"""毎日の価格巡回スクリプト（GitHub Actions から実行）

取得元:
  1. 楽天市場 商品検索API（2026年新方式 openapi.rakuten.co.jp）
      … 環境変数 RAKUTEN_APP_ID（アプリケーションID・UUID形式／必須）
        RAKUTEN_ACCESS_KEY（アクセスキー pk_… ／必須）
        RAKUTEN_AFFILIATE_ID（任意）, SITE_DOMAIN（Referer 用／Webアプリ登録なら必須）
  2. 価格.com 最安価格      … スクレイピング（1機種ごとに待機。失敗しても続行）
  3. Amazon PA-API          … 環境変数 PAAPI_ACCESS_KEY / PAAPI_SECRET_KEY / PAAPI_PARTNER_TAG が
                              揃っている場合のみ（アソシエイト承認後に有効化）

出力:
  data/prices/YYYY-MM-DD.json   その日のスナップショット
  data/price_history.json       機種ID → [{d, amazon, rakuten, kakaku}] の履歴（直近400日）
  data/products.json            各機種の prices フィールドを更新（現在価格・最安履歴）
"""
import json, os, re, sys, time, datetime, urllib.parse, urllib.request, urllib.error, html

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, 'data')
JST = datetime.timezone(datetime.timedelta(hours=9))
TODAY = datetime.datetime.now(JST).strftime('%Y-%m-%d')
UA = 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0 Safari/537.36'

EXCLUDE = re.compile(r'セット|パネル|拡張バッテリー|専用バッテリー|バッグ|ケース|カバー|ケーブル|アダプタ|充電器|収納|保護|中古|整備済|リファービッシュ|レンタル')

# 楽天APIを「Webアプリケーション」タイプで登録した場合、リファラーで許可判定される。
# 自サイトのドメインを Referer として送る（SITE_DOMAIN か RAKUTEN_REFERER で指定）。
REFERER = (os.environ.get('RAKUTEN_REFERER') or
           (('https://' + os.environ['SITE_DOMAIN'].strip().replace('https://', '').strip('/') + '/')
            if os.environ.get('SITE_DOMAIN') else ''))

def errmsg(e):
    body = ''
    try:
        body = e.read().decode('utf-8', 'ignore')[:200]
    except Exception:
        pass
    return f'{type(e).__name__}: {e} {body}'.strip()

def get(url, headers=None, timeout=8):
    h = {'User-Agent': UA}
    if REFERER:
        h['Referer'] = REFERER
        h['Origin'] = REFERER.rstrip('/')
    h.update(headers or {})
    req = urllib.request.Request(url, headers=h)
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
RAKUTEN_ERRORS = []

# 2026年の新API基盤。バージョンは 20260701 が現行、20220601 は移行期の互換用。
RAKUTEN_EPS = ['https://openapi.rakuten.co.jp/ichibams/api/IchibaItem/Search/20260701',
               'https://openapi.rakuten.co.jp/ichibams/api/IchibaItem/Search/20220601']
RAKUTEN_STATE = {'ep': None}     # 最初に通ったエンドポイントを覚える
RAKUTEN_AFF_OFF = {'v': False}   # affiliateId で弾かれたら以降は付けない

def rakuten_call(params):
    eps = [RAKUTEN_STATE['ep']] if RAKUTEN_STATE['ep'] else RAKUTEN_EPS
    last = None
    for ep in eps:
        url = ep + '?' + urllib.parse.urlencode(params)
        for attempt in range(3):
            try:
                js = json.loads(get(url))
                RAKUTEN_STATE['ep'] = ep
                return js
            except urllib.error.HTTPError as e:
                if e.code == 429:          # レート制限は待って再試行
                    time.sleep(2 + attempt * 2)
                    last = e
                    continue
                last = e
                break
            except Exception as e:
                last = e
                break
    raise last

def rakuten_price(p, app_id, aff_id, access_key):
    q, model = query_of(p)
    toks = tokens_of(model)
    base = {'applicationId': app_id, 'keyword': q + ' ポータブル電源',
            'hits': 30, 'sort': '+itemPrice', 'formatVersion': 2}
    if access_key:
        base['accessKey'] = access_key
    params = dict(base)
    if aff_id and not RAKUTEN_AFF_OFF['v']:
        params['affiliateId'] = aff_id
    try:
        js = rakuten_call(params)
    except Exception as e:
        # affiliateId が原因で弾かれるケースがあるので、1度だけ外して再試行
        if 'affiliateId' in params:
            try:
                js = rakuten_call(base)
                RAKUTEN_AFF_OFF['v'] = True
                RAKUTEN_ERRORS.append('affiliateId を外して再試行に成功（アフィリエイトID要確認）')
            except Exception as e2:
                msg = errmsg(e2)[:300]
                if msg not in RAKUTEN_ERRORS:
                    RAKUTEN_ERRORS.append(msg)
                return None, None, f'rakuten error: {e2}'
        else:
            msg = errmsg(e)[:300]
            if msg not in RAKUTEN_ERRORS:
                RAKUTEN_ERRORS.append(msg)
            return None, None, f'rakuten error: {e}'
    if isinstance(js, dict) and js.get('errors'):
        msg = 'API error: ' + json.dumps(js['errors'], ensure_ascii=False)[:200]
        if msg not in RAKUTEN_ERRORS:
            RAKUTEN_ERRORS.append(msg)
        return None, None, msg
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
# 連続で失敗したら以降スキップする（IPブロック等で1件25秒×182件かかるのを防ぐ）
KAKAKU_STATE = {'fail': 0, 'off': os.environ.get('SKIP_KAKAKU') == '1', 'errors': []}
KAKAKU_MAX_FAIL = 8

def kakaku_price(p):
    if KAKAKU_STATE['off']:
        return None, None, 'skipped'
    q, model = query_of(p)
    toks = tokens_of(model)
    url = 'https://search.kakaku.com/' + urllib.parse.quote(q) + '/'
    try:
        body = get(url)
        KAKAKU_STATE['fail'] = 0
    except Exception as e:
        KAKAKU_STATE['fail'] += 1
        msg = errmsg(e)[:300]
        if msg not in KAKAKU_STATE['errors']:
            KAKAKU_STATE['errors'].append(msg)
        if KAKAKU_STATE['fail'] >= KAKAKU_MAX_FAIL:
            KAKAKU_STATE['off'] = True
            print(f'価格.com に {KAKAKU_MAX_FAIL} 回連続で接続できないため、以降スキップします', file=sys.stderr)
        return None, None, f'kakaku error: {e}'
    # 検索結果の各アイテム: タイトルと最安価格
    best = None
    pats = [
        r'<a[^>]+href="(https?://kakaku\.com/item/[^"]+)"[^>]*>([^<]{5,160})</a>[\s\S]{0,3000}?p-item_priceNum[^>]*>[^\d]{0,10}([\d,]{4,9})',
        r'<a[^>]+href="(https?://kakaku\.com/item/[^"]+)"[^>]*>([^<]{5,160})</a>[\s\S]{0,1500}?([\d,]{4,9})\s*円',
    ]
    hits = []
    for pat in pats:
        hits = list(re.finditer(pat, body))
        if hits:
            break
    for m in hits:
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
    access_key = os.environ.get('RAKUTEN_ACCESS_KEY', '')
    if app_id and not access_key:
        print('注意: RAKUTEN_ACCESS_KEY が未設定です（2026年の新方式では必須）', file=sys.stderr)
    if not app_id:
        print('RAKUTEN_APP_ID が未設定です（楽天価格はスキップ）', file=sys.stderr)
    elif not REFERER:
        print('注意: SITE_DOMAIN / RAKUTEN_REFERER が未設定。楽天アプリを「Webアプリケーション」で'
              '登録している場合、リファラー不一致で弾かれることがあります', file=sys.stderr)
    amz = amazon_prices(products)
    snap = {}
    limit = int(os.environ.get('LIMIT', '0') or 0)  # テスト用: 先頭N件だけ
    for i, p in enumerate(products):
        if limit and i >= limit:
            break
        rec = {'d': TODAY}
        if app_id:
            price, url, st = rakuten_price(p, app_id, aff_id, access_key)
            rec['rakuten'] = price
            if url:
                rec['rakuten_url'] = url
            time.sleep(0.25)
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
        time.sleep(0.6 if KAKAKU_STATE['off'] else 1.0)
    os.makedirs(os.path.join(DATA, 'prices'), exist_ok=True)
    json.dump(snap, open(os.path.join(DATA, 'prices', TODAY + '.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    json.dump(history, open(hist_path, 'w', encoding='utf-8'), ensure_ascii=False)
    json.dump(products, open(os.path.join(DATA, 'products.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)

    # ---- 巡回サマリー（data/last_run.json）。毎日ここを見れば成否がわかる ----
    got = lambda k: sum(1 for r in snap.values() if r.get(k))
    summary = {
        'date': TODAY,
        'products': len(snap),
        'rakuten_ok': got('rakuten'),
        'kakaku_ok': got('kakaku'),
        'amazon_ok': got('amazon'),
        'rakuten_app_id_set': bool(app_id),
        'rakuten_access_key_set': bool(access_key),
        'rakuten_endpoint': RAKUTEN_STATE['ep'],
        'rakuten_affiliate_dropped': RAKUTEN_AFF_OFF['v'],
        'rakuten_affiliate_id_set': bool(aff_id),
        'referer': REFERER or '(未設定)',
        'kakaku_skipped': KAKAKU_STATE['off'],
        'kakaku_errors': KAKAKU_STATE['errors'][:5],
        'rakuten_errors': RAKUTEN_ERRORS[:5],
        'paapi_set': all(os.environ.get(k) for k in ('PAAPI_ACCESS_KEY', 'PAAPI_SECRET_KEY', 'PAAPI_PARTNER_TAG')),
    }
    json.dump(summary, open(os.path.join(DATA, 'last_run.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    print('---- 巡回サマリー ----')
    for k, v in summary.items():
        print(f'  {k}: {v}')
    print('done', TODAY)

if __name__ == '__main__':
    main()
