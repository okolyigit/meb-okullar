"""
MEB Okul Listesi
================

MEB "Okullar ve Diğer Kurumlar" sayfasının okul verisini çeken kod. Veri,
sayfanın kullandığı DataTables endpoint'inden alınır:

    POST https://www.meb.gov.tr/baglantilar/okullar/okullar_ajax.php
    gövde: DataTables parametreleri + il=<plaka_kodu> + ilce=<ilce_kodu veya 0>
    yanıt: { recordsTotal, data: [ {OKUL_ADI, HOST, YOL}, ... ] }

OKUL_ADI biçimi: "İL - İLÇE - Okul Adı".

Kullanım:
    from meb import Meb
    m = Meb()
    sanliurfa = m.il(63)
    okullar = sanliurfa.okullar()
    m.tocsv('sanliurfa.csv', [sanliurfa])
"""

import csv
import json
import logging
import re
import time
from urllib.parse import urlencode

import urllib3

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
_formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
_ch = logging.StreamHandler()
_ch.setFormatter(_formatter)
logger.addHandler(_ch)

http = urllib3.PoolManager()

ENDPOINT = 'https://www.meb.gov.tr/baglantilar/okullar/okullar_ajax.php'

# Plaka kodu -> İl adı (endpoint "il" parametresi plaka kodunu bekler)
IL_KODLARI = {
    '1': 'Adana', '2': 'Adıyaman', '3': 'Afyonkarahisar', '4': 'Ağrı',
    '5': 'Amasya', '6': 'Ankara', '7': 'Antalya', '8': 'Artvin',
    '9': 'Aydın', '10': 'Balıkesir', '11': 'Bilecik', '12': 'Bingöl',
    '13': 'Bitlis', '14': 'Bolu', '15': 'Burdur', '16': 'Bursa',
    '17': 'Çanakkale', '18': 'Çankırı', '19': 'Çorum', '20': 'Denizli',
    '21': 'Diyarbakır', '22': 'Edirne', '23': 'Elazığ', '24': 'Erzincan',
    '25': 'Erzurum', '26': 'Eskişehir', '27': 'Gaziantep', '28': 'Giresun',
    '29': 'Gümüşhane', '30': 'Hakkari', '31': 'Hatay', '32': 'Isparta',
    '33': 'Mersin', '34': 'İstanbul', '35': 'İzmir', '36': 'Kars',
    '37': 'Kastamonu', '38': 'Kayseri', '39': 'Kırklareli', '40': 'Kırşehir',
    '41': 'Kocaeli', '42': 'Konya', '43': 'Kütahya', '44': 'Malatya',
    '45': 'Manisa', '46': 'Kahramanmaraş', '47': 'Mardin', '48': 'Muğla',
    '49': 'Muş', '50': 'Nevşehir', '51': 'Niğde', '52': 'Ordu',
    '53': 'Rize', '54': 'Sakarya', '55': 'Samsun', '56': 'Siirt',
    '57': 'Sinop', '58': 'Sivas', '59': 'Tekirdağ', '60': 'Tokat',
    '61': 'Trabzon', '62': 'Tunceli', '63': 'Şanlıurfa', '64': 'Uşak',
    '65': 'Van', '66': 'Yozgat', '67': 'Zonguldak', '68': 'Aksaray',
    '69': 'Bayburt', '70': 'Karaman', '71': 'Kırıkkale', '72': 'Batman',
    '73': 'Şırnak', '74': 'Bartın', '75': 'Ardahan', '76': 'Iğdır',
    '77': 'Yalova', '78': 'Karabük', '79': 'Kilis', '80': 'Osmaniye',
    '81': 'Düzce',
}

_HEADERS = {
    'Content-Type': 'application/x-www-form-urlencoded',
    'X-Requested-With': 'XMLHttpRequest',
    'User-Agent': 'Mozilla/5.0',
    'Referer': 'https://www.meb.gov.tr/baglantilar/okullar/index.php',
}


_TR_UPPER = {'I': 'ı', 'İ': 'i', 'Ş': 'ş', 'Ç': 'ç', 'Ö': 'ö', 'Ü': 'ü', 'Ğ': 'ğ'}
_TR_LOWER = {'i': 'İ', 'ı': 'I', 'ş': 'Ş', 'ç': 'Ç', 'ö': 'Ö', 'ü': 'Ü', 'ğ': 'Ğ'}


def _tr_lower(ch):
    return _TR_UPPER.get(ch, ch.lower())


def _tr_upper(ch):
    return _TR_LOWER.get(ch, ch.upper())


def capitalize(string):
    """Türkçe-duyarlı başlık biçimi (I->ı, İ->i; birleşik nokta bırakmaz)."""
    words = []
    for s in str(string).split(' '):
        if not s:
            continue
        head = _tr_upper(s[0])
        tail = ''.join(_tr_lower(c) for c in s[1:])
        words.append(head + tail)
    return " ".join(words)


def _strip_tags(value):
    if value is None:
        return None
    return re.sub(r'<[^>]+>', '', str(value)).strip() or None


class Okul:
    def __repr__(self):
        return "<Okul: %s>" % self.ad

    def __init__(self, record, il_adi=None):
        """okullar_ajax.php yanıtındaki bir kayıttan Okul oluşturur.

        Alanlar: OKUL_ADI ("İL - İLÇE - Okul Adı"), HOST, YOL.
        HOST okulun web alan adı (ya da kurum kodu); YOL ile tam adres kurulur.

        il_adi verilirse (sorgulanan ilin resmi adı) il, metinden parse edilen
        yazıma göre değil bu değere göre alınır; böylece kaynaktaki yazım
        tutarsızlıkları ("Afyon"/"Afyonkarahisar" gibi) tek isimde birleşir.
        """
        self.raw = record
        il, self.ilce, self.ad = self._parse_ad(_strip_tags(record.get('OKUL_ADI')) or '')
        self.il = il_adi or il
        self.host = _strip_tags(record.get('HOST'))
        self.yol = _strip_tags(record.get('YOL'))
        self.website = self._build_url(self.host)
        self.type = self._type(self.ad)

    @staticmethod
    def _build_url(host):
        host = (host or '').strip()
        if not host or host in ('#', '-'):
            return None
        if host.startswith('http://') or host.startswith('https://'):
            return host
        # HOST nokta içeriyorsa tam alan adıdır; yoksa MEB k12 alt alan adı kuralı.
        if '.' in host:
            return 'https://' + host.lstrip('/')
        return 'https://%s.meb.k12.tr' % host

    @staticmethod
    def _parse_ad(kurum_adi):
        """OKUL_ADI -> (il, ilce, ad). Biçim: "İL - İLÇE - Okul Adı".

        Okul adının kendisinde de " - " geçebileceği için yalnızca ilk iki
        ayraç il/ilçe olarak alınır, kalanı okul adıdır.
        """
        ad = re.sub(r'\s+', ' ', kurum_adi.strip())
        parts = ad.split(' - ')
        if len(parts) >= 3:
            il, ilce = parts[0], parts[1]
            okul = ' - '.join(parts[2:])
        elif len(parts) == 2:
            il, ilce, okul = parts[0], '', parts[1]
        else:
            il, ilce, okul = '', '', ad
        return capitalize(il.strip()), capitalize(ilce.strip()), okul.strip()

    def as_dict(self):
        return {
            'il_adi': self.il,
            'ilce_adi': self.ilce,
            'okul_adi': self.ad,
            'tip': self.type,
            'okul_website': self.website,
            'host': self.host,
            'yol': self.yol,
        }

    def _type(self, ad):
        MESLEK_LISESI = "Mesleki Eğitim Merkezi|MESLEKİ EĞİTİM MERKEZİ|" \
                        "Teknik Eğitim Merkezi|MESLEKİ EĞİTİM MERKEZ|" \
                        "Mesleki Eğitimi Merkezi|Turizm Eğitim Merkezi|" \
                        "TURİZM EĞİTİM MERKEZİ|EğitimUygulama|" \
                        "TEKNİK EĞİTİM MERKEZİ|Tekin Mes|Eğitim  Merkezi|" \
                        "Mes\\.Eğt|Eğitim Enstitüsü|"

        OGRETMENEVI = "ÖĞRETMENEVİ MÜDÜRLÜĞÜ|ÖĞRETMENEVİ|Öğretmenevi|" \
                      "Öğretmen Evi|ÖĞRETMEN EVİ|Ögretmen Evi|Öğretmeni"

        if re.findall("Ortaokul|ORTAOKUL|Orta Okul|ortaokul|ORTOKULU|Ortaoku|Ortakulu|ORTA OKULU|Ortaoklu|ORTAOOKULU|Ortaoklulu|Ortokulu", ad):
            return "Ortaokul"
        elif re.findall('ilkokul|İlkokul|İLKOKUL|İlköğretim|Ilkokulu|İlokulu|İlkokolu|İlk Okulu|İlkolkulu|İLOKULU|İLK OKULU|İkokulu|İlkkulu|İllkokulu|İlköğ', ad):
            return "İlkokul"
        elif re.findall("Lise|lise|LİSE", ad):
            return "Lise"
        elif re.findall("Sanat Okulu|Sanat Merkezi|SANAT OKULU|SANAT MERKEZİ|Akşam Sanat Ok|sanat Merkezi", ad):
            return "Sanat Okulu"
        elif re.findall("Halk Eğitim|HALK EĞİTİMİ MERKEZİ|Halk Eğt|HALK EĞİTİM MERKEZİ", ad):
            return "Halk Eğitim Merkezi"
        elif re.findall("Anaokulu|anaokulu|ANAOKULU|ANA OKULU|OKUL ÖNCESİ|ANAOKU|Ana Okulu", ad):
            return "Anaokulu"
        elif re.findall("Araştırma Merkezi|ARAŞTIRMA MERKEZİ|Araştırma  Merkezi", ad):
            return "Araştırma Merkezi"
        elif re.findall("Eğitim Müdürlüğü|EĞİTİM MÜDÜRLÜĞÜ", ad):
            return "Milli Eğitim Müdürlüğü"
        elif re.findall(MESLEK_LISESI, ad):
            return "Meslek Lisesi"
        elif re.findall("Uygulama Merkezi|UYGULAMA MERKEZİ", ad):
            return "Uygulama Merkezi"
        elif re.findall("Olgunlaşma Enstitüsü", ad):
            return "Olgunlaşma Enstitüsü"
        elif re.findall(OGRETMENEVI, ad):
            return "Öğretmenevi"
        elif re.findall("YBO", ad):
            return "Yatılı Bölge Okulu"
        else:
            return None


class Il:
    def __str__(self):
        return str(self.ad)

    def __repr__(self):
        return "<Il: %s (%s)>" % (self.ad, self.kod)

    def __init__(self, kod, ad=None):
        self.kod = str(kod)
        self.ad = ad or IL_KODLARI.get(self.kod, self.kod)

    def _page(self, ilce, start, length, draw):
        params = {
            'draw': draw, 'start': start, 'length': length,
            'il': self.kod, 'ilce': ilce,
            'search[value]': '', 'search[regex]': 'false',
            'order[0][column]': 0, 'order[0][dir]': 'asc',
        }
        for i in range(3):  # tabloda 3 kolon var, hepsi OKUL_ADI'na bağlı
            params['columns[%d][data]' % i] = 'OKUL_ADI'
            params['columns[%d][name]' % i] = ''
            params['columns[%d][searchable]' % i] = 'true'
            params['columns[%d][orderable]' % i] = 'true' if i == 0 else 'false'
            params['columns[%d][search][value]' % i] = ''
            params['columns[%d][search][regex]' % i] = 'false'
        body = urlencode(params)
        # Endpoint kararsız: çoğu zaman 200 + boş gövde ya da 500 döner; tekrar dene.
        last = None
        for attempt in range(10):
            try:
                resp = http.request('POST', ENDPOINT, body=body,
                                    headers=_HEADERS, timeout=30.0)
                if resp.status == 200 and resp.data:
                    return json.loads(resp.data.decode('utf-8'))
                last = 'HTTP %s, %d bayt' % (resp.status, len(resp.data))
            except Exception as e:
                last = str(e)
            time.sleep(2)
        raise RuntimeError('%s yanıt vermedi (%s)' % (ENDPOINT, last))

    def okullar(self, ilce_kodu=0, page_size=1000):
        """
        İlin (isteğe bağlı: tek bir ilçenin) okullarını döner.
        :param ilce_kodu: 0/boş -> ildeki tüm okullar; dolu -> sadece o ilçe
        :return: [Okul, ...]
        """
        logger.info('%s (%s) okulları indiriliyor...' % (self.ad, self.kod))
        okullar = []
        start, draw = 0, 1
        total = None
        try:
            while True:
                d = self._page(ilce_kodu, start, page_size, draw)
                rows = d.get('data', []) if isinstance(d, dict) else d
                if total is None and isinstance(d, dict):
                    total = d.get('recordsTotal') or d.get('recordsFiltered')
                okullar.extend(Okul(r, il_adi=self.ad) for r in rows)
                draw += 1
                if not rows or (total is not None and len(okullar) >= int(total)):
                    break
                if len(rows) < page_size:  # son sayfa
                    break
                start += page_size
        except Exception:
            logger.exception('%s okulları indirilemedi!' % self.ad)
            raise
        logger.info('%s: %d okul bulundu.' % (self.ad, len(okullar)))
        return okullar


class Meb:
    def __init__(self):
        self.iller = [Il(k, v) for k, v in sorted(IL_KODLARI.items(), key=lambda kv: int(kv[0]))]

    def il(self, kod):
        """Plaka koduna göre Il döner. Örn: m.il(63) -> Şanlıurfa"""
        kod = str(kod)
        for il in self.iller:
            if il.kod == kod:
                return il
        return Il(kod)

    def okullar(self):
        """Türkiye genelindeki tüm okulları döner (uzun sürer)."""
        schools = []
        for il in self.iller:
            schools.extend(il.okullar())
        return schools

    def tocsv(self, filename, iller=None):
        """Verilen illerin (varsayılan: tümü) okullarını CSV'ye yazar."""
        iller = iller if iller is not None else self.iller
        fieldnames = ['il_adi', 'ilce_adi', 'okul_adi', 'tip',
                      'okul_website', 'host', 'yol']
        counter = 0
        with open(filename, 'w', newline='', encoding='utf-8') as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            writer.writeheader()
            for il in iller:
                for okul in il.okullar():
                    writer.writerow(okul.as_dict())
                    counter += 1
        logger.info("Toplam yazılan okul sayısı: %s" % counter)
        return counter
