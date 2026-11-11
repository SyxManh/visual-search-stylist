"""Traditional birth-year colour suggestions; local calculations, Vietnam UTC+7.

Calendar rules: months begin on a local new-moon day; month 11 contains the
winter solstice; a leap month has no principal solar term. Phase approximation
uses Meeus' new-moon equations (J2000 epoch), with TT->UT delta-T correction.
This module is independently implemented from the astronomical equations.
"""
from datetime import date, datetime, timedelta, timezone
from functools import lru_cache
from math import sin, radians, floor
import re

VN_TIME = timezone(timedelta(hours=7))
EPOCH = date(2000, 1, 1)


def today_vn():
    return datetime.now(VN_TIME).date()


def parse_birth_date(value):
    if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        raise ValueError("Chọn ngày sinh dương lịch đầy đủ ngày, tháng, năm.")
    try:
        result = date.fromisoformat(value)
    except ValueError:
        raise ValueError("Ngày sinh không hợp lệ.") from None
    if not date(1900, 1, 1) <= result <= today_vn():
        raise ValueError("Ngày sinh phải từ năm 1900 đến hôm nay.")
    return result


def _jd(value):
    return (value - EPOCH).days + 2451545


def _delta_t(year):
    # NASA polynomial approximations, seconds; used only in the supported era.
    if year < 1920:
        t = year - 1900
        return -2.79 + 1.494119*t - .0598939*t*t + .0061966*t**3 - .000197*t**4
    if year < 1941:
        t = year - 1920
        return 21.20 + .84493*t - .076100*t*t + .0020936*t**3
    if year < 1961:
        t = year - 1950
        return 29.07 + .407*t - t*t/233 + t**3/2547
    if year < 1986:
        t = year - 1975
        return 45.45 + 1.067*t - t*t/260 - t**3/718
    if year < 2005:
        t = year - 2000
        return 63.86 + .3345*t - .060374*t*t + .0017275*t**3 + .000651814*t**4 + .00002373599*t**5
    t = year - 2000
    return 62.92 + .32217*t + .005589*t*t


@lru_cache(maxsize=2500)
def _moon_day(k):
    t = k / 1236.85
    e = 1 - .002516*t - .0000074*t*t
    m = 2.5534 + 29.10535670*k - .0000014*t*t - .00000011*t**3
    p = 201.5643 + 385.81693528*k + .0107582*t*t + .00001238*t**3 - .000000058*t**4
    f = 160.7108 + 390.67050284*k - .0016118*t*t - .00000227*t**3 + .000000011*t**4
    omega = 124.7746 - 1.56375580*k + .0020672*t*t + .00000215*t**3
    terms = [(-.40720,p),(.17241*e,m),(.01608,2*p),(.01039,2*f),
             (.00739*e,p-m),(-.00514*e,p+m),(.00208*e*e,2*m),
             (-.00111,p-2*f),(-.00057,p+2*f),(.00056*e,2*p+m),
             (-.00042,3*p),(.00042*e,m+2*f),(.00038*e,m-2*f),
             (-.00024*e,2*p-m),(-.00017,omega),(-.00007,p+2*m),
             (.00004,2*p-2*f),(.00004,3*m),(.00003,p+m-2*f),
             (.00003,2*p+2*f),(-.00003,p+m+2*f),(.00003,p-m+2*f),
             (-.00002,p-m-2*f),(-.00002,3*p+m),(.00002,4*p)]
    jde = 2451550.09765 + 29.530588853*k + .0001337*t*t - .000000150*t**3 + .00000000073*t**4
    jde += sum(a*sin(radians(angle)) for a,angle in terms)
    # Small planetary corrections from the phase equations.
    planetary = [(.000325,299.77+.107408*k-.009173*t*t),(.000165,251.88+.016321*k),
                 (.000164,251.83+26.651886*k),(.000126,349.42+36.412478*k),
                 (.000110,84.66+18.206239*k),(.000062,141.74+53.303771*k),
                 (.000060,207.14+2.453732*k),(.000056,154.84+7.306860*k),
                 (.000047,34.52+27.261239*k),(.000042,207.19+.121824*k),
                 (.000040,291.34+1.844379*k),(.000037,161.72+24.198154*k),
                 (.000035,239.56+25.513099*k),(.000023,331.55+3.592518*k)]
    jde += sum(a*sin(radians(angle)) for a,angle in planetary)
    return floor(jde - _delta_t(2000+k/12.3685)/86400 + .5 + 7/24)


def _sector(local_jd):
    t = (local_jd - .5 - 7/24 - 2451545)/36525
    m = 357.52911 + 35999.05029*t - .0001537*t*t
    longitude = 280.46646 + 36000.76983*t + .0003032*t*t
    longitude += (1.914602-.004817*t-.000014*t*t)*sin(radians(m))
    longitude += (.019993-.000101*t)*sin(radians(2*m)) + .000289*sin(radians(3*m))
    return floor((longitude % 360)/30)


def _month_eleven(year):
    k = floor((_jd(date(year,12,31))-2451550.09765)/29.530588853)
    if _sector(_moon_day(k)) >= 9:
        k -= 1
    return k, _moon_day(k)


def lunar_year_for_date(value):
    day = _jd(value)
    k = floor((day-2451550.09765)/29.530588853)
    while _moon_day(k+1) <= day:
        k += 1
    while _moon_day(k) > day:
        k -= 1
    anchor_k, anchor = _month_eleven(value.year)
    if anchor >= _moon_day(k):
        year = value.year
        anchor_k, anchor = _month_eleven(year-1)
        _, end = _month_eleven(year)
    else:
        year = value.year+1
        _, end = _month_eleven(year)
    offset = k-anchor_k
    month = offset+11
    if end-anchor > 365:
        previous = _sector(_moon_day(anchor_k+1))
        leap = 0
        for n in range(2,15):
            current = _sector(_moon_day(anchor_k+n))
            if current == previous:
                leap = n-1
                break
            previous = current
        if leap and offset >= leap:
            month -= 1
    if month > 12:
        month -= 12
    if month >= 11 and offset < 4:
        year -= 1
    return year


NAP_AM = [
    ("Hải Trung Kim","Kim"),("Lư Trung Hỏa","Hỏa"),("Đại Lâm Mộc","Mộc"),
    ("Lộ Bàng Thổ","Thổ"),("Kiếm Phong Kim","Kim"),("Sơn Đầu Hỏa","Hỏa"),
    ("Giản Hạ Thủy","Thủy"),("Thành Đầu Thổ","Thổ"),("Bạch Lạp Kim","Kim"),
    ("Dương Liễu Mộc","Mộc"),("Tuyền Trung Thủy","Thủy"),("Ốc Thượng Thổ","Thổ"),
    ("Tích Lịch Hỏa","Hỏa"),("Tùng Bách Mộc","Mộc"),("Trường Lưu Thủy","Thủy"),
    ("Sa Trung Kim","Kim"),("Sơn Hạ Hỏa","Hỏa"),("Bình Địa Mộc","Mộc"),
    ("Bích Thượng Thổ","Thổ"),("Kim Bạch Kim","Kim"),("Phú Đăng Hỏa","Hỏa"),
    ("Thiên Hà Thủy","Thủy"),("Đại Trạch Thổ","Thổ"),("Thoa Xuyến Kim","Kim"),
    ("Tang Đố Mộc","Mộc"),("Đại Khê Thủy","Thủy"),("Sa Trung Thổ","Thổ"),
    ("Thiên Thượng Hỏa","Hỏa"),("Thạch Lựu Mộc","Mộc"),("Đại Hải Thủy","Thủy"),
]
PALETTES = {
    "Kim": [("Trắng","#F8FAFC"),("Xám bạc","#94A3B8")],
    "Mộc": [("Xanh lá","#16A34A"),("Xanh rêu","#657A35")],
    "Thủy": [("Xanh navy","#1E3A5F"),("Đen","#171717")],
    "Hỏa": [("Đỏ","#DC2626"),("Hồng","#EC4899"),("Tím","#9333EA")],
    "Thổ": [("Vàng đất","#CA8A04"),("Nâu","#92400E")],
}
SUPPORT = {"Kim":"Thổ","Mộc":"Thủy","Thủy":"Kim","Hỏa":"Mộc","Thổ":"Hỏa"}
TRADITION_NOTE = "Gợi ý theo quan niệm ngũ hành truyền thống, dùng làm cảm hứng phối màu; không có bằng chứng khoa học về tác động đến vận may. Bạn vẫn có thể chọn mọi màu mình thích."


def birth_palette(value):
    birth = parse_birth_date(value)
    year = lunar_year_for_date(birth)
    stem = ["Giáp","Ất","Bính","Đinh","Mậu","Kỷ","Canh","Tân","Nhâm","Quý"][(year-4)%10]
    branch = ["Tý","Sửu","Dần","Mão","Thìn","Tỵ","Ngọ","Mùi","Thân","Dậu","Tuất","Hợi"][(year-4)%12]
    name, element = NAP_AM[((year-1984)%60)//2]
    colors = [{"label":label,"hex":color,"relation":relation}
              for group,relation in [(element,"Cùng hành"),(SUPPORT[element],"Tương sinh")]
              for label,color in PALETTES[group]]
    return {"lunar_year":year,"can_chi":f"{stem} {branch}","nap_am":name,"element":element,
            "colors":colors,"note":TRADITION_NOTE,
            "method":"Mệnh nạp âm theo năm âm lịch, đổi năm tại Tết theo múi giờ Việt Nam (UTC+7). Đây là gợi ý theo năm sinh, không phải lá số Bát tự."}
