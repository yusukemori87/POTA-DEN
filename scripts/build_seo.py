"""SEO用の追加ページを生成する（build.py の最後から exec で呼ばれ、build.py のグローバル変数をそのまま使う）。
   - docs/guide/<slug>/  用途別ランキング記事
   - docs/guide/         記事一覧
   - docs/brand/<slug>/  ブランド別の全機種ページ
   - トップページに静的リンク（全機種・用途別・ブランド別）を差し込む（JS無しでもクロールできるように）
   - 各機種ページに「関連機種」「この機種が入っているランキング」を差し込む
   - sitemap.xml を全ページ入りで作り直し、lastmod を実際の更新日にする"""
import json, os, html, re, datetime

_e = lambda s: html.escape(str(s if s is not None else ''), quote=True)
_fmt = lambda n: '—' if n is None else f'{n:,}'
_yen = lambda n: '—' if n is None else '¥' + f'{n:,}'

# ---------- 共通の値 ----------
def _cur(p):
    pr = p.get('prices') or {}
    return pr.get('min') or p.get('amazon_price') or p.get('price_jpy')

def _low(p):
    pr = p.get('prices') or {}
    c = _cur(p)
    xs = [x for x in [p.get('sale_low_price'), pr.get('hist_min'), c] if x]
    return min(xs) if xs else None

def _ppw(p):
    c = _cur(p)
    return round(c / p['capacity_wh'], 1) if c and p.get('capacity_wh') else None

def _score(p):
    return (p.get('tenno') or {}).get('score') or 0

for _i, _p in enumerate(prods):
    _p['_i'] = _i
    _p['_slug'] = slug(_p['brand'], _p['model'])
    _p['_fn'] = full_name(_p['brand'], _p['model'])
    _p['_cur'] = _cur(_p)
    _p['_ppw'] = _ppw(_p)

LIVE = [p for p in prods if not p.get('discontinued')]

BRAND_SLUG_FIX = {'JVCケンウッド': 'jvc-kenwood'}
def brand_slug(b):
    if b in BRAND_SLUG_FIX:
        return BRAND_SLUG_FIX[b]
    s = re.sub(r'[^a-z0-9]+', '-', b.lower()).strip('-')
    return s or 'brand'

BRANDS = {}
for p in prods:
    BRANDS.setdefault(p['brand'], []).append(p)

# ---------- 用途別ランキングの定義 ----------
# intro / how / faq は編集部の解説文。リストはデータから毎日自動で並び替わる。
GUIDES = [
 dict(slug='bousai', short='防災・停電対策',
  title='防災・停電対策におすすめのポータブル電源ランキング',
  kw='防災 停電 ポータブル電源 おすすめ',
  filt=lambda p: (p.get('capacity_wh') or 0) >= 1000 and (p.get('rated_output_w') or 0) >= 1000 and (p.get('battery') or '').upper().startswith('LFP'),
  crit='容量1,000Wh以上・定格出力1,000W以上・リン酸鉄（LFP）電池',
  intro=('停電のときに頼れるのは「冷蔵庫を止めない」「スマホと照明を何日か回せる」容量です。家庭用の冷蔵庫は平均すると40〜60W前後で動くので、'
         '1,000Whあれば冷蔵庫だけでおよそ半日〜1日、2,000Whなら照明やスマホ充電を足しても1日以上もちます。'
         '電池は長期保管に強く劣化しにくいリン酸鉄（LFP）が前提。普段は押し入れで眠っていて、年に数回だけ出番が来る使い方だからです。'),
  how=['家族2〜3人なら1,000〜1,500Wh、4人以上や在宅医療機器がある家は2,000Wh以上を目安にする',
       '電子レンジ・ドライヤー・電気ケトルを使うなら定格1,500W以上（電力リフト等の抵抗負荷モードがあると楽）',
       'ソーラー入力が大きい機種なら、停電が長引いても昼に充電して夜に使う回し方ができる',
       '保証年数とサポートの評判は必ず見る。災害時に「動かない」が一番困る'],
  faq=[('防災用は何Whあれば足りますか？', '冷蔵庫・照明・スマホ充電を1日まかなうなら1,000〜1,500Whが目安です。冷蔵庫の消費電力は機種で倍以上違うので、手持ちの冷蔵庫の年間消費電力量（kWh/年）を365で割ると1日分のWhがわかります。'),
       ('ずっと満充電で保管しても大丈夫？', 'LFP電池は劣化しにくいですが、メーカーの多くは60〜80%程度での保管と、3〜6か月に一度の充放電を推奨しています。UPS機能付きなら普段からコンセントにつないでおく使い方もできます。'),
       ('ソーラーパネルも買うべき？', '停電が3日を超える想定なら有効です。曇りでは発電量が大きく落ちるので、パネルは本体のソーラー入力上限に近い出力を選ぶと回復が早くなります。')]),
 dict(slug='shachuhaku', short='車中泊',
  title='車中泊におすすめのポータブル電源ランキング',
  kw='車中泊 ポータブル電源 おすすめ',
  filt=lambda p: 500 <= (p.get('capacity_wh') or 0) <= 1600 and (p.get('weight_kg') or 99) <= 15 and (p.get('rated_output_w') or 0) >= 500,
  crit='容量500〜1,600Wh・重量15kg以下・定格出力500W以上',
  intro=('車中泊の電気は「電気毛布で朝まで」「ポータブル冷蔵庫を一晩」「スマホとPCの充電」が基本セットです。電気毛布は弱で30〜50W程度なので8時間で240〜400Wh、'
         'ポータブル冷蔵庫も一晩で200〜400Whほど使います。1泊なら500〜800Wh、連泊やエアコンのない夏冬の車中泊なら1,000Wh以上が安心です。'
         '車内は積み下ろしが多いので、容量と同じくらい重さが効いてきます。'),
  how=['1泊なら500〜800Wh、2泊以上や家族での車中泊は1,000〜1,500Wh',
       '15kgを超えると車への積み下ろしがつらい。女性一人で運ぶなら10kg前後まで',
       'シガーソケット充電（走行充電）に対応しているかを確認する。走りながら回復できると連泊が楽',
       '冬の車中泊は低温で出力が落ちる機種もあるので、レビューの低温時の報告を見る'],
  faq=[('電気毛布は一晩でどのくらい使いますか？', '弱〜中で30〜60W前後の製品が多く、8時間で240〜480Whが目安です。容量の8割程度が実際に使える量なので、500Wh機なら電気毛布1枚で一晩はほぼ確実にもちます。'),
       ('車のシガーソケットで充電できますか？', '多くの機種が対応していますが、シガー充電は100〜120W程度と遅く、1,000Whを満充電するには10時間前後かかります。走行充電を重視するなら専用の走行充電器（オルタネーターチャージャー）に対応した機種が有利です。'),
       ('夏の車内に置きっぱなしにしても平気？', '真夏の車内は60℃を超えることがあり、ほとんどの機種で保管温度の上限を超えます。日陰や断熱バッグに入れ、長時間の放置は避けてください。')]),
 dict(slug='camp', short='キャンプ',
  title='キャンプにおすすめのポータブル電源ランキング',
  kw='キャンプ ポータブル電源 おすすめ',
  filt=lambda p: 250 <= (p.get('capacity_wh') or 0) <= 1100 and (p.get('weight_kg') or 99) <= 12,
  crit='容量250〜1,100Wh・重量12kg以下',
  intro=('キャンプでは「サイトまで運べるか」が最初の条件になります。オートキャンプでも駐車場から何往復もするので、10kg前後が実用の上限です。'
         'スマホ・ランタン・扇風機・小型の電気毛布くらいなら300〜700Whで1泊2日をまかなえます。'
         '電気ケトルやホットプレートを使いたい人は、容量より定格出力（1,000W以上）を先に見てください。'),
  how=['ソロ〜デュオで充電中心なら300〜500Wh、ファミリーで電気毛布や調理家電も使うなら700Wh以上',
       '重量は10kg前後までが現実的。ハンドルの形や大きさも持ち運びやすさに効く',
       '調理家電を使うなら定格出力1,000W以上か、電力リフト等の抵抗負荷モードがあるか',
       '昼にソーラーで補充するなら、ソーラー入力が大きい機種ほど回復が早い'],
  faq=[('キャンプで電気ケトルは使えますか？', '電気ケトルは1,000〜1,300W前後なので、定格出力がそれ以上ある機種が必要です。一部の機種には、定格を超える抵抗負荷を電圧を下げて動かすモード（電力リフト・X-Boost等）があり、時間はかかりますがお湯を沸かせます。'),
       ('雨の日でも使えますか？', 'ほとんどのポータブル電源は防水ではありません。テントやタープの下で使い、地面からの湿気を避けるために台やマットの上に置いてください。'),
       ('キャンプ場に電源サイトがあれば不要？', '電源サイトがあれば必須ではありませんが、電源サイトは料金が高く数も少ないので、ポータブル電源があるとサイト選びの幅が広がります。')]),
 dict(slug='keiryo', short='軽量・小型',
  title='軽量・小型のポータブル電源ランキング（6kg以下）',
  kw='ポータブル電源 軽量 小型 おすすめ',
  filt=lambda p: (p.get('weight_kg') or 99) <= 6 and (p.get('capacity_wh') or 0) >= 150,
  crit='重量6kg以下・容量150Wh以上',
  intro=('6kg以下は片手で気軽に持ち出せる重さです。スマホやノートPCの充電、扇風機、LEDランタン、ルーター用の簡易UPSといった軽い用途なら、このクラスで十分です。'
         'ただし小型機は「容量あたりの価格」が高くなりがちで、同じお金を出すなら大きい機種のほうがWh単価は安くなります。'
         '持ち運ぶ頻度が高い人ほど、このクラスを選ぶ価値があります。'),
  how=['スマホ・PCの充電がメインなら200〜300Whで十分',
       'USB-Cの最大出力（PD 100W以上か）を見ると、ノートPCの充電速度がわかる',
       'Wh単価は高めになりやすいので、セール時の価格で比べる',
       '小型でもLFP電池の機種を選ぶと、長く使える'],
  faq=[('飛行機に持ち込めますか？', '国内線・国際線ともに、160Whを超えるリチウムイオン電池は持ち込みも預け入れもできません。100Wh超〜160Wh以下は条件付きで2個までです。このページの機種の多くは160Whを超えるため、航空機には載せられません。'),
       ('モバイルバッテリーとの違いは？', 'ポータブル電源はAC（家庭用コンセント）出力を備え、家電を動かせる点が違います。スマホ充電だけならモバイルバッテリーのほうが軽くて安く済みます。')]),
 dict(slug='cospa', short='コスパ（Wh単価）',
  title='コスパで選ぶポータブル電源ランキング（Wh単価が安い順）',
  kw='ポータブル電源 コスパ 安い おすすめ',
  filt=lambda p: _score(p) >= 70 and p.get('_ppw'),
  sort=lambda p: p['_ppw'],
  crit='総合評価70点以上の機種を、Wh単価（実売価格÷容量）の安い順に',
  intro=('ポータブル電源の値段を比べるときは、本体価格ではなく「1Whあたりいくらか（Wh単価）」で見るのが一番公平です。'
         '容量が違う機種同士でも、同じ物差しで割安かどうかがわかります。ただし安いだけで品質に問題がある機種もあるため、'
         'このランキングは編集部の総合評価70点以上の機種だけに絞ってから、Wh単価の安い順に並べています。価格は毎日自動で更新しています。'),
  how=['Wh単価50円/Wh台は「かなり安い」、100円/Wh前後が平均的、150円/Wh超は割高',
       'セール時はWh単価が3〜4割下がる機種も多い。「セール最安」の値も確認する',
       '保証年数が短い機種は、安くても長期的には割高になることがある',
       '容量が大きい機種ほどWh単価は下がりやすい。必要な容量を決めてから比べる'],
  faq=[('Wh単価はどう計算していますか？', 'Amazon・楽天・価格.comで取得した当日の最安値を容量（Wh）で割った値です。毎朝自動で再計算しています。'),
       ('一番安い時期はいつですか？', 'Amazonのプライムデー（7月）とブラックフライデー（11月末）、メーカー公式の周年セールで大きく下がる傾向があります。各機種ページの「セール時最安値」が過去に確認できた最安の目安です。')]),
 dict(slug='daiyoryo', short='大容量（2,000Wh以上）',
  title='大容量ポータブル電源ランキング（2,000Wh以上）',
  kw='ポータブル電源 大容量 2000Wh おすすめ',
  filt=lambda p: (p.get('capacity_wh') or 0) >= 2000,
  crit='容量2,000Wh以上',
  intro=('2,000Wh以上のクラスは、停電時に家の電気をある程度まるごと肩代わりできる「家庭用蓄電池の入口」です。'
         '冷蔵庫・照明・テレビ・スマホを丸1日以上動かせ、電子レンジやエアコンまで動かせる高出力機も多くなります。'
         '一方で20kgを超える機種がほとんどで、持ち運ぶというより「キャスターで転がす」「置きっぱなしにする」使い方が前提になります。'),
  how=['エアコンや電子レンジを動かすなら定格2,000W以上、IHや井戸ポンプなら200V出力対応も検討',
       '拡張バッテリーに対応していると、あとから容量を増やせる',
       '重量とキャスターの有無を確認する。25kgを超えると一人で持ち上げるのは厳しい',
       '太陽光パネルや分電盤とつなぐ予定があるなら、ソーラー入力と家庭用接続オプションを見る'],
  faq=[('家庭用蓄電池の代わりになりますか？', '停電時のバックアップとしては代わりになります。ただし家庭用蓄電池のように分電盤へ自動でつなぐには、専用の切替器や工事が必要な機種がほとんどです。'),
       ('エアコンは動きますか？', '6畳用のエアコンは運転中400〜600W前後、起動時に一時的に大きな電力を使います。定格2,000W級の機種なら動かせることが多く、2,000Whあれば3〜4時間が目安です。')]),
 dict(slug='200v', short='200V出力対応',
  title='200V出力対応のポータブル電源ランキング',
  kw='ポータブル電源 200V 対応',
  filt=lambda p: bool(p.get('v200')),
  crit='200V出力に対応（本体または連結・専用アダプタ）',
  intro=('200V出力に対応したポータブル電源なら、停電時に200Vのエアコン・IHクッキングヒーター・井戸ポンプ・電気温水器の一部まで動かせます。'
         '対応機種はまだ少なく、2台連結や専用ボックスで200Vにする方式もあります。'
         '200V機器は消費電力が大きいので、容量と定格出力にも余裕のある機種を選ぶ必要があります。'),
  how=['200Vの出し方（本体単体／2台連結／専用ボックス）を確認する。追加費用が大きく変わる',
       '動かしたい機器の定格消費電力より、定格出力に余裕があるか',
       'コンセントの形状（200V用のプラグ形状）が合うか',
       '分電盤経由で家に給電する場合は電気工事が必要'],
  faq=[('200Vのエアコンを動かせますか？', '対応機種の定格出力内であれば動かせます。ただしコンセントの形状が合わない場合は変換や工事が必要です。必ずメーカーの対応表を確認してください。')]),
 dict(slug='solar', short='ソーラー充電向き',
  title='ソーラー充電向きのポータブル電源ランキング',
  kw='ポータブル電源 ソーラー 充電 おすすめ',
  filt=lambda p: (p.get('capacity_wh') or 0) >= 500 and p.get('solar_input_w') and p['solar_input_w'] / p['capacity_wh'] >= 0.55,
  crit='容量500Wh以上・ソーラー最大入力が容量の0.55倍以上',
  intro=('太陽光で充電して使う「オフグリッド」な使い方では、容量よりもソーラー入力の大きさが効いてきます。'
         '晴れた日の実発電はパネル定格の6〜7割ほどで、日照もおよそ4〜5時間分です。ソーラー入力が容量の半分以上あれば、天気の良い日に1日でほぼ満充電に戻せます。'
         'このランキングは、容量に対してソーラー入力が大きい機種だけを集めました。'),
  how=['ソーラー入力（W）÷容量（Wh）が0.5以上なら、晴天1日で満充電に近づく',
       '入力電圧の範囲（Voc）を確認する。パネルを直列にするときに上限を超えないように',
       'パネルは本体の入力上限に近い合計出力を用意すると、曇りの日も回復しやすい',
       '自家消費やオフグリッド生活に使うなら、サイクル寿命（3,000回以上）と保証年数も重視'],
  faq=[('ソーラーパネルは何Wを選べばいい？', '本体のソーラー入力上限と同じくらいの合計出力が理想です。実際の発電はパネル定格の6〜7割程度になるので、上限より少し大きめに組んでも入力は上限で頭打ちになるだけで、壊れることは通常ありません（電圧の上限は必ず守ってください）。'),
       ('メーカーの違うパネルも使えますか？', 'コネクタ形状（MC4・XT60・Anderson等）と電圧範囲が合えば使えることが多いです。ただしメーカー保証の対象外になる場合があります。')]),
]

def guide_items(g):
    xs = [p for p in LIVE if g['filt'](p)]
    if g.get('sort'):
        xs.sort(key=g['sort'])
    else:
        xs.sort(key=lambda p: (-_score(p), p.get('_ppw') or 9e9))
    return xs[:15]

for g in GUIDES:
    g['items'] = guide_items(g)

IN_GUIDES = {}
for g in GUIDES:
    for p in g['items']:
        IN_GUIDES.setdefault(p['_slug'], []).append(g)

# ---------- ページ共通パーツ ----------
EXTRA_CSS = ('.art{max-width:880px;margin:0 auto;padding:8px 0 40px}.art h1{font-size:26px;line-height:1.35;margin:6px 0 12px}'
 '.art h2{font-size:19px;margin:34px 0 10px;padding-bottom:6px;border-bottom:1px solid var(--line)}'
 '.art p,.art li{line-height:1.85;font-size:15px}.art .upd{font-size:12px;color:var(--muted)}'
 '.rk{border:1px solid var(--line);border-radius:12px;padding:16px 18px;margin:14px 0;display:grid;grid-template-columns:96px 1fr;gap:16px}'
 '.rk img{width:96px;height:96px;object-fit:contain}.rk .no{font-family:var(--mono);font-size:12px;color:var(--muted)}'
 '.rk h3{margin:2px 0 6px;font-size:17px}.rk h3 a{color:inherit}.rk .sp{font-size:13px;color:var(--ink2);margin:4px 0}'
 '.rk .vd{font-weight:600;margin:6px 0 4px}.rk .bd{font-size:14px;line-height:1.8;margin:0}.rk .sc{font-weight:700;color:#0E7C66}'
 '.tbl{width:100%;border-collapse:collapse;font-size:13px;margin:10px 0}.tbl th,.tbl td{border-bottom:1px solid var(--line);padding:7px 6px;text-align:left;vertical-align:top}'
 '.tbl th{color:var(--muted);font-weight:600;white-space:nowrap}.tbl td.n{text-align:right;white-space:nowrap}'
 '.lnk{display:flex;flex-wrap:wrap;gap:8px;padding:0;list-style:none}.lnk li a{display:inline-block;padding:6px 12px;border:1px solid var(--line2,var(--line));border-radius:999px;font-size:13px;text-decoration:none;color:inherit}'
 '.allp{columns:3 220px;font-size:13px;line-height:1.9}.allp h3{font-size:13px;margin:10px 0 2px;break-after:avoid}.allp ul{margin:0;padding-left:1.1em}'
 '.faq dt{font-weight:700;margin-top:14px}.faq dd{margin:4px 0 0;line-height:1.8}'
 '.rel{margin:28px 0 8px}.rel h2{font-size:15px;margin:0 0 8px}'
 '@media(max-width:600px){.rk{grid-template-columns:64px 1fr}.rk img{width:64px;height:64px}}')

FONTS = ('<link rel="preconnect" href="https://fonts.googleapis.com">'
         '<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=IBM+Plex+Sans+JP:wght@400;500;600;700&family=IBM+Plex+Mono:wght@500;600&display=swap">')

def topbar():
    return (f'<div class="top"><div class="topin"><a class="logo" href="{SITE}/" style="text-decoration:none;color:inherit">'
            '<i></i>ポタ電カタログ<small>JAPAN</small></a></div></div>')

def guide_nav(exclude=None):
    lis = ''.join(f'<li><a href="{SITE}/guide/{g["slug"]}/">{_e(g["short"])}</a></li>' for g in GUIDES if g['slug'] != exclude)
    return f'<ul class="lnk">{lis}</ul>'

def brand_nav():
    bs = sorted(BRANDS, key=lambda b: -len(BRANDS[b]))
    lis = ''.join(f'<li><a href="{SITE}/brand/{brand_slug(b)}/">{_e(b)}（{len(BRANDS[b])}）</a></li>' for b in bs)
    return f'<ul class="lnk">{lis}</ul>'

FOOT = ('<footer style="padding:24px 0 40px;color:var(--ink2);font-size:12px;max-width:80ch">'
        '価格はAmazon・楽天・価格.comの最安値を毎日自動取得しています。「総合評価（天の声）」は編集部がレビューを横断して読み、仕様・価格・保証・サポート報告を突き合わせて付けた独自の辛口採点です。'
        '本ページのリンクにはアフィリエイトリンクを含みます。<b>Amazonのアソシエイトとして、ポタ電カタログは適格販売により収入を得ています。</b>'
        '価格は取得時点のもので変動します。最新の価格・在庫は各販売ページでご確認ください。</footer>')

def page(title, desc, canon, body, ld_list=()):
    lds = ''.join(f'<script type="application/ld+json">{json.dumps(x, ensure_ascii=False)}</script>' for x in ld_list)
    head = (f'<title>{_e(title)}</title><meta name="description" content="{_e(desc)}"><link rel="canonical" href="{canon}">'
            f'<meta property="og:type" content="article"><meta property="og:title" content="{_e(title)}">'
            f'<meta property="og:description" content="{_e(desc)}"><meta property="og:url" content="{canon}">'
            f'<meta property="og:site_name" content="ポタ電カタログ"><meta property="og:locale" content="ja_JP">'
            f'<meta property="og:image" content="{OG_IMAGE}"><meta name="twitter:card" content="summary_large_image">'
            f'<meta name="theme-color" content="#0E7C66">{ICONS}{FONTS}{lds}'
            f'<style>{PAGE_CSS}</style><style>{EXTRA_CSS}</style>')
    return (f'<!doctype html><html lang="ja"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">{head}</head>'
            f'<body>{topbar()}<div class="page" style="grid-template-columns:1fr;max-width:1000px"><main>{body}{FOOT}</main></div></body></html>')

def crumbs_ld(items):
    return {"@context": "https://schema.org", "@type": "BreadcrumbList",
            "itemListElement": [{"@type": "ListItem", "position": i + 1, "name": n, "item": u} for i, (n, u) in enumerate(items)]}

def crumbs_html(items):
    return ('<nav style="font-size:12px;color:var(--muted);margin-bottom:10px">' +
            ' ＞ '.join(f'<a href="{u}">{_e(n)}</a>' if u else _e(n) for n, u in items) + '</nav>')

def spec_line(p):
    bits = [f"{_fmt(p.get('capacity_wh'))}Wh"]
    if p.get('rated_output_w'):
        bits.append(f"定格{_fmt(p['rated_output_w'])}W")
    if p.get('solar_input_w'):
        bits.append(f"ソーラー{_fmt(p['solar_input_w'])}W")
    if p.get('weight_kg') is not None:
        bits.append(f"{p['weight_kg']}kg")
    if p.get('battery'):
        bits.append(p['battery'])
    if p.get('warranty_years'):
        bits.append(f"保証{p['warranty_years']}年")
    return '／'.join(bits)

def rank_card(n, p):
    t = p.get('tenno') or {}
    img = IMG.get(str(p['_i'])) or (p.get('prices') or {}).get('image')
    url = f"{SITE}/p/{p['_slug']}/"
    low = _low(p)
    price = f"実売 {_yen(p['_cur'])}" + (f"（Wh単価 {p['_ppw']}円）" if p.get('_ppw') else '')
    if low and p['_cur'] and low < p['_cur'] * 0.98:
        price += f"・セール最安 {_yen(low)}"
    body = (t.get('body') or '')
    if len(body) > 170:
        body = body[:170].rsplit('。', 1)[0] + '。'
    return (f'<div class="rk"><a href="{url}">' + (f'<img src="{img}" alt="{_e(p["_fn"])}" loading="lazy" width="96" height="96">' if img else '') +
            f'</a><div><div class="no">第{n}位・総合評価 <span class="sc">{_score(p)}点</span></div>'
            f'<h3><a href="{url}">{_e(p["_fn"])}</a></h3><div class="sp">{_e(spec_line(p))}</div><div class="sp">{_e(price)}</div>'
            f'<div class="vd">{_e(t.get("verdict"))}</div><p class="bd">{_e(body)}</p>'
            + (f'<div class="sp">向いている人：{_e(t.get("best_for"))}</div>' if t.get('best_for') else '') +
            f'<div class="sp"><a href="{url}">{_e(p["_fn"])}の詳しいレビューと最安値を見る →</a></div></div></div>')

def cmp_table(xs):
    rows = ''.join(
        f'<tr><td><a href="{SITE}/p/{p["_slug"]}/">{_e(p["_fn"])}</a></td><td class="n">{_score(p)}</td>'
        f'<td class="n">{_fmt(p.get("capacity_wh"))}</td><td class="n">{_fmt(p.get("rated_output_w"))}</td>'
        f'<td class="n">{p.get("weight_kg") if p.get("weight_kg") is not None else "—"}</td>'
        f'<td class="n">{_yen(p["_cur"])}</td><td class="n">{p.get("_ppw") or "—"}</td></tr>' for p in xs)
    return ('<div style="overflow-x:auto"><table class="tbl"><thead><tr><th>機種</th><th>評価</th><th>容量Wh</th><th>定格W</th>'
            f'<th>重量kg</th><th>実売</th><th>円/Wh</th></tr></thead><tbody>{rows}</tbody></table></div>')

new_urls = []   # (url, lastmod)

# ---------- 用途別ランキング ----------
for g in GUIDES:
    xs = g['items']
    url = f"{SITE}/guide/{g['slug']}/"
    n_all = len([p for p in LIVE if g['filt'](p)])
    title = f"{g['title']}【{TODAY[:4]}年最新・{len(xs)}選】｜ポタ電カタログ"
    top3 = '、'.join(p['_fn'] for p in xs[:3])
    desc = (f"{g['short']}向けのポータブル電源を{N}機種から厳選。条件は{g['crit']}。1位は{top3.split('、')[0] if xs else ''}。"
            f"上位は{top3}。辛口の総合評価・実売価格・Wh単価で比較、価格は毎日更新。")[:158]
    cr = [('ポタ電カタログ', f'{SITE}/'), ('用途別ランキング', f'{SITE}/guide/'), (g['short'], url)]
    body = (crumbs_html(cr) + '<article class="art">'
            f'<h1>{_e(g["title"])}</h1><div class="upd">最終更新：{TODAY}（価格は毎朝自動更新）・ポタ電カタログ編集部</div>'
            f'<p>{_e(g["intro"])}</p>'
            f'<h2>選び方のポイント</h2><ul>' + ''.join(f'<li>{_e(x)}</li>' for x in g['how']) + '</ul>'
            f'<h2>ランキングの条件</h2><p>掲載{N}機種のうち、販売中で「{_e(g["crit"])}」を満たす{n_all}機種を、'
            + ('Wh単価の安い順' if g.get('sort') else '編集部の総合評価（天の声・100点満点）の高い順') +
            f'に並べました（上位{len(xs)}機種）。評価は実際の購入者レビューの不具合報告・保証・サポートの評判まで反映した辛口の採点です。</p>'
            f'<h2>{_e(g["short"])}向け 比較表</h2>{cmp_table(xs)}'
            f'<h2>{_e(g["short"])}向け ランキング{len(xs)}選</h2>' + ''.join(rank_card(i + 1, p) for i, p in enumerate(xs)) +
            ('<h2>よくある質問</h2><dl class="faq">' + ''.join(f'<dt>{_e(q)}</dt><dd>{_e(a)}</dd>' for q, a in g['faq']) + '</dl>' if g.get('faq') else '') +
            f'<div class="rel"><h2>ほかの用途別ランキング</h2>{guide_nav(g["slug"])}</div>'
            f'<div class="rel"><h2>ブランドから探す</h2>{brand_nav()}</div>'
            f'<p><a class="btn" href="{SITE}/">全{N}機種を条件で絞り込んで比較する →</a></p></article>')
    lds = [crumbs_ld(cr),
           {"@context": "https://schema.org", "@type": "ItemList", "name": g['title'], "numberOfItems": len(xs),
            "itemListElement": [{"@type": "ListItem", "position": i + 1, "name": p['_fn'], "url": f"{SITE}/p/{p['_slug']}/"} for i, p in enumerate(xs)]},
           {"@context": "https://schema.org", "@type": "Article", "headline": g['title'], "dateModified": TODAY, "inLanguage": "ja",
            "author": {"@type": "Organization", "name": "ポタ電カタログ編集部"}, "publisher": {"@type": "Organization", "name": "ポタ電カタログ"},
            "mainEntityOfPage": url}]
    if g.get('faq'):
        lds.append({"@context": "https://schema.org", "@type": "FAQPage", "mainEntity": [
            {"@type": "Question", "name": q, "acceptedAnswer": {"@type": "Answer", "text": a}} for q, a in g['faq']]})
    d_ = os.path.join(ROOT, 'docs', 'guide', g['slug'])
    os.makedirs(d_, exist_ok=True)
    open(os.path.join(d_, 'index.html'), 'w', encoding='utf-8').write(page(title, desc, url, body, lds))
    new_urls.append((url, TODAY))

# ---------- 記事一覧 ----------
_gurl = f'{SITE}/guide/'
_gb = (crumbs_html([('ポタ電カタログ', f'{SITE}/'), ('用途別ランキング', None)]) + '<article class="art">'
       '<h1>用途別 ポータブル電源ランキング一覧</h1>'
       f'<p>ポタ電カタログに掲載している{N}機種を、使い道ごとの条件で絞り込んで辛口の総合評価順に並べたランキングです。価格とWh単価は毎朝自動で更新しています。</p>'
       + ''.join(f'<h2><a href="{SITE}/guide/{g["slug"]}/" style="color:inherit">{_e(g["title"])}</a></h2>'
                 f'<p>{_e(g["intro"][:110].rsplit("。",1)[0] + "。")}</p>'
                 f'<p class="upd">条件：{_e(g["crit"])}／1位：' + (f'<a href="{SITE}/p/{g["items"][0]["_slug"]}/">{_e(g["items"][0]["_fn"])}</a>' if g['items'] else '—') + '</p>'
                 for g in GUIDES) +
       f'<div class="rel"><h2>ブランドから探す</h2>{brand_nav()}</div></article>')
os.makedirs(os.path.join(ROOT, 'docs', 'guide'), exist_ok=True)
open(os.path.join(ROOT, 'docs', 'guide', 'index.html'), 'w', encoding='utf-8').write(
    page(f'用途別 ポータブル電源ランキング一覧｜ポタ電カタログ', f'防災・車中泊・キャンプ・軽量・コスパ・大容量・200V・ソーラー充電の用途別に、ポータブル電源{N}機種を辛口採点で比較したランキング一覧。', _gurl, _gb,
         [crumbs_ld([('ポタ電カタログ', f'{SITE}/'), ('用途別ランキング', _gurl)])]))
new_urls.append((_gurl, TODAY))

# ---------- ブランド別 ----------
for b, xs in BRANDS.items():
    xs = sorted(xs, key=lambda p: (bool(p.get('discontinued')), -_score(p)))
    live = [p for p in xs if not p.get('discontinued')]
    url = f"{SITE}/brand/{brand_slug(b)}/"
    sc = [_score(p) for p in live if _score(p)]
    avg = round(sum(sc) / len(sc)) if sc else None
    best = live[0] if live else None
    cheap = min((p for p in live if p.get('_ppw')), key=lambda p: p['_ppw'], default=None)
    title = f"{b}のポータブル電源 全{len(xs)}機種の比較・評価・最安値｜ポタ電カタログ"
    desc = (f"{b}のポータブル電源{len(xs)}機種（販売中{len(live)}機種）を辛口採点・実売価格・Wh単価で比較。"
            + (f"総合評価トップは{best['_fn']}（{_score(best)}点）。" if best else '') + "価格は毎日更新。")[:158]
    cr = [('ポタ電カタログ', f'{SITE}/'), (f'{b}', url)]
    summary = (f'<p>ポタ電カタログでは{_e(b)}のポータブル電源を{len(xs)}機種掲載しています（うち販売中{len(live)}機種）。'
               + (f'販売中モデルの総合評価の平均は{avg}点で、' if avg else '')
               + (f'もっとも評価が高いのは<a href="{SITE}/p/{best["_slug"]}/">{_e(best["_fn"])}</a>（{_score(best)}点・{_e((best.get("tenno") or {}).get("verdict"))}）です。' if best else '')
               + (f'Wh単価がもっとも安いのは<a href="{SITE}/p/{cheap["_slug"]}/">{_e(cheap["_fn"])}</a>（{cheap["_ppw"]}円/Wh）。' if cheap else '') + '</p>')
    body = (crumbs_html(cr) + '<article class="art">'
            f'<h1>{_e(b)}のポータブル電源 全{len(xs)}機種の比較</h1><div class="upd">最終更新：{TODAY}（価格は毎朝自動更新）</div>'
            + summary +
            f'<h2>{_e(b)} 全機種の比較表</h2>{cmp_table(live)}' +
            (f'<h2>{_e(b)} 評価の高い順</h2>' + ''.join(rank_card(i + 1, p) for i, p in enumerate(live)) if live else '') +
            ('<h2>販売終了・流通在庫のみのモデル</h2><ul>' + ''.join(f'<li><a href="{SITE}/p/{p["_slug"]}/">{_e(p["_fn"])}</a>（{_e(spec_line(p))}）</li>' for p in xs if p.get('discontinued')) + '</ul>'
             if any(p.get('discontinued') for p in xs) else '') +
            f'<div class="rel"><h2>用途別ランキング</h2>{guide_nav()}</div>'
            f'<div class="rel"><h2>ほかのブランド</h2>{brand_nav()}</div></article>')
    d_ = os.path.join(ROOT, 'docs', 'brand', brand_slug(b))
    os.makedirs(d_, exist_ok=True)
    open(os.path.join(d_, 'index.html'), 'w', encoding='utf-8').write(
        page(title, desc, url, body, [crumbs_ld(cr), {"@context": "https://schema.org", "@type": "ItemList", "name": f'{b}のポータブル電源',
              "itemListElement": [{"@type": "ListItem", "position": i + 1, "name": p['_fn'], "url": f"{SITE}/p/{p['_slug']}/"} for i, p in enumerate(xs)]}]))
    new_urls.append((url, TODAY))

# ---------- 機種ページに関連リンクを差し込む ----------
def related(p):
    same = [q for q in BRANDS[p['brand']] if q is not p and not q.get('discontinued')]
    same.sort(key=lambda q: abs((q.get('capacity_wh') or 0) - (p.get('capacity_wh') or 0)))
    cap = p.get('capacity_wh') or 0
    near = [q for q in LIVE if q is not p and q['brand'] != p['brand'] and cap and 0.7 * cap <= (q.get('capacity_wh') or 0) <= 1.4 * cap]
    near.sort(key=lambda q: -_score(q))
    return same[:6], near[:8]

def li(q):
    return (f'<li><a href="{SITE}/p/{q["_slug"]}/">{_e(q["_fn"])}</a>'
            f'<span style="color:var(--muted)">（{_fmt(q.get("capacity_wh"))}Wh・{_score(q)}点・{_yen(q["_cur"])}）</span></li>')

for p in prods:
    fp = os.path.join(ROOT, 'docs', 'p', p['_slug'], 'index.html')
    if not os.path.exists(fp):
        continue
    h = open(fp, encoding='utf-8').read()
    same, near = related(p)
    gs = IN_GUIDES.get(p['_slug'], [])
    blk = '<section class="art" style="max-width:none;padding:0">'
    if gs:
        blk += ('<div class="rel"><h2>この機種が入っているランキング</h2><ul class="lnk">' +
                ''.join(f'<li><a href="{SITE}/guide/{g["slug"]}/">{_e(g["short"])}（{g["items"].index(p) + 1}位）</a></li>' for g in gs) + '</ul></div>')
    if near:
        blk += f'<div class="rel"><h2>同じくらいの容量のライバル機種</h2><ul>{"".join(li(q) for q in near)}</ul></div>'
    if same:
        blk += (f'<div class="rel"><h2>{_e(p["brand"])}のほかの機種</h2><ul>{"".join(li(q) for q in same)}</ul>'
                f'<p><a href="{SITE}/brand/{brand_slug(p["brand"])}/">{_e(p["brand"])}の全{len(BRANDS[p["brand"]])}機種を比較する →</a></p></div>')
    blk += f'<div class="rel"><h2>用途別ランキング</h2>{guide_nav()}</div></section>'
    # パンくずにブランドを挟む
    h = h.replace(f'<a href="{SITE}/">ポタ電カタログ</a> ＞ ',
                  f'<a href="{SITE}/">ポタ電カタログ</a> ＞ <a href="{SITE}/brand/{brand_slug(p["brand"])}/">{_e(p["brand"])}</a> ＞ ', 1)
    h = h.replace('<footer style="padding:24px 0 40px', blk + '<footer style="padding:24px 0 40px', 1)
    h = h.replace('</head>', f'<style>{EXTRA_CSS}</style></head>', 1)
    open(fp, 'w', encoding='utf-8').write(h)

# ---------- トップページに静的リンクを差し込む ----------
_ip = os.path.join(ROOT, 'docs', 'index.html')
_ih = open(_ip, encoding='utf-8').read()
_bs = sorted(BRANDS, key=lambda b: -len(BRANDS[b]))
_all = ''.join(f'<h3><a href="{SITE}/brand/{brand_slug(b)}/">{_e(b)}</a></h3><ul>' +
               ''.join(f'<li><a href="{SITE}/p/{q["_slug"]}/">{_e(q["_fn"])}</a></li>' for q in sorted(BRANDS[b], key=lambda q: q.get('capacity_wh') or 0)) + '</ul>'
               for b in _bs)
_seo = (f'<section class="art" style="max-width:none;padding:24px 0 0"><style>{EXTRA_CSS}</style>'
        f'<div class="rel"><h2>用途別ランキング</h2>{guide_nav()}</div>'
        f'<div class="rel"><h2>ブランドから探す</h2>{brand_nav()}</div>'
        f'<div class="rel"><h2>全{N}機種の一覧</h2><div class="allp">{_all}</div></div></section>')
_ih = _ih.replace('</main>', _seo + '</main>', 1)
open(_ip, 'w', encoding='utf-8').write(_ih)

# ---------- sitemap（lastmod は価格が最後に動いた日） ----------
_hist_path = os.path.join(ROOT, 'data', 'price_history.json')
HIST = json.load(open(_hist_path, encoding='utf-8')) if os.path.exists(_hist_path) else {}
def last_change(i):
    h = HIST.get(str(i)) or []
    last, prev = None, None
    for r in h:
        v = (r.get('amazon'), r.get('rakuten'), r.get('kakaku'))
        if v != prev:
            last = r.get('d')
        prev = v
    return last or TODAY

sm = [(f'{SITE}/', TODAY)] + new_urls + [(f"{SITE}/p/{p['_slug']}/", last_change(p['_i'])) for p in prods]
open(os.path.join(ROOT, 'docs', 'sitemap.xml'), 'w', encoding='utf-8').write(
    '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n' +
    ''.join(f'<url><loc>{u}</loc><lastmod>{m}</lastmod></url>\n' for u, m in sm) + '</urlset>\n')
print(f'SEO: guide {len(GUIDES)}本 + brand {len(BRANDS)}本 + 機種ページ関連リンク + sitemap {len(sm)}URL')
