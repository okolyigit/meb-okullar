# Meb Okulları Listesi

[Milli Eğitim Bakanlığı](https://www.meb.gov.tr/baglantilar/okullar/)
web sitesindeki illerin okul listesini çeken python kodu.

## Hazır Veri

Kodu çalıştırmak istemeyenler için tüm Türkiye'nin güncel okul listesi
[`meb-okullar.csv`](meb-okullar.csv) dosyasında hazır bulunur:
**81 il, 54.940 okul**. Kolonlar: `il_adi, ilce_adi, okul_adi, tip,
okul_website, host, yol`.

Veri, sayfanın kullandığı DataTables endpoint'inden alınır:

```text
POST https://www.meb.gov.tr/baglantilar/okullar/okullar_ajax.php
gövde: DataTables parametreleri + il=<plaka_kodu> + ilce=<ilce_kodu veya 0>
yanıt: { recordsTotal, data: [ { "OKUL_ADI", "HOST", "YOL" }, ... ] }
```

- `il` parametresi **plaka kodu**dur (örn. Şanlıurfa = 63).
- `OKUL_ADI` biçimi: `"İL - İLÇE - Okul Adı"`; `HOST` + `YOL` ile okulun web adresi kurulur.
- Endpoint zaman zaman boş gövde ya da `HTTP 500` döndürebildiği için her sayfa
  birkaç kez yeniden denenir; veri gelene kadar bir-iki saniye sürebilir.

## Gereksinimler

- Python 3.6 =>
- urllib3

```
pip install -r requirements.txt
```

## Kullanım

```python
from meb import Meb

m = Meb()
m.iller                 # 81 il (plaka kodu ile)
# [<Il: Adana (1)>, ..., <Il: Şanlıurfa (63)>, ...]
```

### Tek Bir İlin Okulları (örn. Şanlıurfa = 63)

```python
sanliurfa = m.il(63)               # ya da m.il('63')
okullar = sanliurfa.okullar()      # Şanlıurfa'daki tüm okullar

okul = okullar[0]
okul.__dict__
# {'il': 'Şanlıurfa', 'ilce': 'Akçakale',
#  'ad': 'Abdulkadir Yüceltaş Anaokulu',
#  'host': '...', 'yol': '...',
#  'website': 'https://...meb.k12.tr',
#  'type': 'Anaokulu', 'raw': {...}}

# CSV'ye yazma
m.tocsv('sanliurfa_okullar.csv', [sanliurfa])
```

CSV kolonları: `il_adi, ilce_adi, okul_adi, tip, okul_website, host, yol`

### Tek Bir İlçenin Okulları

```python
# ilce_kodu, MEB il sayfasındaki ilçe (ILCEKODU) değeridir.
akcakale = m.il(63).okullar(ilce_kodu='575')
```

### Tüm Türkiye

```python
m.okullar()                 # tüm illerin okulları (uzun sürer)
m.tocsv('meb-okullar.csv')  # hepsini CSV'ye yazar
```

## Okul Tipleri

`Okul.type` alanı okul adından çıkarılır:

- None (Belirlenemeyen)
- Anaokulu
- İlkokul
- Ortaokul
- Lise
- Sanat Okulu
- Halk Eğitim Merkezi
- Araştırma Merkezi
- Milli Eğitim Müdürlüğü
- Meslek Lisesi
- Uygulama Merkezi
- Olgunlaşma Enstitüsü
- Öğretmenevi
- Yatılı Bölge Okulu
