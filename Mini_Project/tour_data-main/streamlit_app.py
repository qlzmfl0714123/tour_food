import streamlit as st
import pandas as pd
import requests
import time
import os
import re
import io
import textwrap
from PIL import Image
import base64
import streamlit.components.v1 as components
from dotenv import load_dotenv
from math import radians, sin, cos, sqrt, atan2

# 🔧 환경 변수 로드
load_dotenv()
google_key = os.getenv("Google_key")
kakao_key = os.getenv("KAKAO_KEY")

# ✅ 좌표 거리 계산
def haversine(lat1, lon1, lat2, lon2):
    R = 6371e3
    phi1, phi2 = radians(lat1), radians(lat2)
    dphi = radians(lat2 - lat1)
    dlambda = radians(lon2 - lon1)
    a = sin(dphi/2)**2 + cos(phi1)*cos(phi2)*sin(dlambda/2)**2
    return 2 * R * atan2(sqrt(a), sqrt(1-a))

# ✅ 구글 Place Details API → 전화번호 가져오기
def get_place_details(place_id, api_key):
    url = "https://maps.googleapis.com/maps/api/place/details/json"
    params = {"place_id": place_id, "fields": "name,formatted_address,formatted_phone_number", "language": "ko", "key": api_key}
    res = requests.get(url, params=params).json()
    return res.get("result", {})

# ✅ Kakao place_id 가져오기
def get_kakao_place_id(name, lat, lng, kakao_key, address="", phone=None):
    url = "https://dapi.kakao.com/v2/local/search/keyword.json"
    headers = {"Authorization": f"KakaoAK {kakao_key}"}

    queries = []
    if phone:
        queries.append(phone)

    korean = re.sub(r"[^가-힣]", "", name)
    region = ""
    if "시" in address:
        region = address.split("시")[0] + "시"
    elif "도" in address:
        region = address.split("도")[0] + "도"

    if korean:
        queries.append(f"{region} {korean}")
    else:
        queries.append(f"{region} {name}")

    best_doc, best_dist = None, float("inf")

    for q in queries:
        params = {"query": q, "x": lng, "y": lat, "radius": 300}
        res = requests.get(url, headers=headers, params=params).json()

        if not res.get("documents"):
            continue

        for d in res["documents"]:
            dist = haversine(lat, lng, float(d["y"]), float(d["x"]))
            if dist < best_dist:
                best_dist = dist
                best_doc = d

        if best_doc and best_dist < 100:
            break

    return best_doc["id"] if best_doc else None

# ✅ 관광지 검색
def search_places(query, api_key):
    url = "https://maps.googleapis.com/maps/api/place/textsearch/json"
    params = {'query': f"{query} 관광지", 'language': 'ko', 'key': api_key}
    res = requests.get(url, params=params).json()
    return [p for p in res.get('results', []) if p.get('user_ratings_total', 0) >= 50]

# ✅ 위도/경도 조회
def get_lat_lng(address, api_key):
    url = "https://maps.googleapis.com/maps/api/geocode/json"
    params = {'address': address, 'language': 'ko', 'key': api_key}
    res = requests.get(url, params=params).json()
    if res.get('status') == 'OK' and res['results']:
        loc = res['results'][0]['geometry']['location']
        return loc['lat'], loc['lng']
    return None, None

# ✅ 사진 URL
def get_place_photo_url(photo_reference, api_key, maxwidth=400):
    return f"https://maps.googleapis.com/maps/api/place/photo?maxwidth={maxwidth}&photoreference={photo_reference}&key={api_key}"

# ✅ 리뷰 여러 개 가져오기
def get_reviews(place_id, api_key, max_reviews=3):
    url = "https://maps.googleapis.com/maps/api/place/details/json"
    params = {'place_id': place_id, 'fields': 'review', 'language': 'ko', 'key': api_key}
    try:
        res = requests.get(url, params=params).json()
        reviews = res.get('result', {}).get('reviews', [])
        return sorted(reviews, key=lambda x: x.get('time', 0), reverse=True)[:max_reviews]
    except:
        return []

# ✅ 리뷰 HTML 렌더링
def render_reviews(reviews):
    review_blocks = []
    for r in reviews:
        author = r.get('author_name', '익명')
        rating = r.get('rating', '')
        text = textwrap.shorten(r.get('text', ''), width=80, placeholder='…')
        block = f"<div style='background:#f1f1f1; border-radius:8px; padding:10px; margin-top:5px;'>"
        block += f"<b>{author}</b> ⭐ {rating}<br><span style='font-size:14px;'>{text}</span></div>"
        review_blocks.append(block)
    return "".join(review_blocks)

# ✅ 맛집 검색 (전화번호 포함)
def find_nearby_restaurants(lat, lng, api_key, radius=2000):
    url = "https://maps.googleapis.com/maps/api/place/nearbysearch/json"
    params = {'location': f'{lat},{lng}', 'radius': radius, 'type': 'restaurant', 'language': 'ko', 'key': api_key}
    res = requests.get(url, params=params).json()
    time.sleep(1)

    restaurants = []
    for r in res.get("results", [])[:15]:
        name = r.get("name")
        address = r.get("vicinity")
        r_lat = r["geometry"]["location"]["lat"]
        r_lng = r["geometry"]["location"]["lng"]

        place_id_google = r.get("place_id")  # 🔧 추가
        phone = None
        if place_id_google:
            details = get_place_details(place_id_google, api_key)
            phone = details.get("formatted_phone_number")

        place_id_kakao = get_kakao_place_id(name, r_lat, r_lng, kakao_key, address, phone)

        restaurants.append({
            "이름": name,
            "주소": address,
            "평점": r.get("rating", "없음"),
            "위도": r_lat,
            "경도": r_lng,
            "전화번호": phone if phone else "없음",
            "place_id": place_id_kakao,
            "place_id_google": place_id_google,  # 🔧 추가
            "photos": r.get("photos")
        })
    return restaurants

# ✅ 데이터 전처리
def preprocess_restaurant_data(df):
    df['이름'] = df['이름'].astype(str).str.strip()
    df = df[~df['이름'].isin(['-', '없음', '', None])]
    df = df.drop_duplicates(subset='이름')
    df['평점'] = pd.to_numeric(df['평점'], errors='coerce')
    df = df.dropna(subset=['평점'])
    df['주소'] = df['주소'].astype(str).str.strip()
    df['주소'] = df['주소'].str.replace(r'^KR, ?', '', regex=True)
    df['주소'] = df['주소'].str.replace(r'^South Korea,?\s*', '', regex=True)
    df['주소'] = df['주소'].str.rstrip('/')
    df = df[~df['주소'].apply(lambda x: bool(re.fullmatch(r'[A-Za-z0-9 ,.-]+', x)))]
    df = df[df['주소'].str.strip() != '']
    df = df.dropna(subset=['주소'])
    df = df.loc[df['평점'] > 3.5]
    df = df.sort_values(by='평점', ascending=False)
    return df.reset_index(drop=True)

# ✅ 관광지 카드 출력
def display_top_attractions(places):
    st.markdown("---")
    st.markdown("#### ⭐ 추천 관광지 Top 5")
    cols = st.columns(5)
    for idx, place in enumerate(places[:5]):
        with cols[idx]:
            name = place.get('name', '')
            rating = place.get('rating', '')
            address = place.get('formatted_address', '')
            place_id = place.get('place_id')
            link = f"https://www.google.com/maps/place/?q=place_id:{place_id}"
            photo_url = get_place_photo_url(place['photos'][0]['photo_reference'], google_key) if place.get('photos') else ""
            reviews = get_reviews(place_id, google_key, 1)
            review_html = render_reviews(reviews)
            st.markdown(f"""
                <div style='background:#f9f9f9; padding:10px; border-radius:10px; height:460px;'>
                    <div style='display:flex; justify-content:space-between;'>
                        <b>{name}</b> <a href='{link}' target='_blank'>🔗</a>
                    </div>
                    <img src='{photo_url}' style='width:100%; height:120px; object-fit:cover; border-radius:8px;'>
                    <div style='text-align:center; color:#f39c12;'>⭐ {rating}</div>
                    <div style='font-size:13px; text-align:center;'>{address}</div>
                    {review_html}
                </div>
            """, unsafe_allow_html=True)

# ✅ 맛집 카드 출력
def display_top_restaurants(df):
    st.markdown("---")
    st.markdown("#### 🍽 추천 맛집 Top 5")
    top = df.head(5)
    cols = st.columns(5)
    for idx, row in top.iterrows():
        with cols[idx]:
            name = row['이름']
            rating = row['평점']
            address = row['주소']
            photo_url = get_place_photo_url(row['photos'][0]['photo_reference'], google_key) if row.get('photos') else ""
            reviews = get_reviews(row['place_id_google'], google_key, 1) if row.get('place_id_google') else []  # 🔧 수정
            review_html = render_reviews(reviews)
            st.markdown(f"""
                <div style='background:#f9f9f9; padding:10px; border-radius:10px; height:460px;'>
                    <div style='display:flex; justify-content:space-between;'>
                        <b>{name}</b>
                    </div>
                    <img src='{photo_url}' style='width:100%; height:120px; object-fit:cover; border-radius:8px;'>
                    <div style='text-align:center; color:#f39c12;'>⭐ {rating}</div>
                    <div style='font-size:13px; text-align:center;'>{address}</div>
                    {review_html}
                </div>
            """, unsafe_allow_html=True)

# ✅ 메인 실행
def main():
    st.set_page_config(layout="wide")
    st.title("📍 MatTour😋")

    query = st.text_input("가고 싶은 지역을 입력하세요", "제주")

    if st.button("관광지 검색"):
        st.session_state.places = search_places(query, google_key)
        st.session_state.selected_place = None

    if "places" in st.session_state and st.session_state.places:
        display_top_attractions(st.session_state.places)

        st.markdown("---")
        st.markdown("<h5 style='font-size:22px;'>📌 관광지를 선택하세요</h5>", unsafe_allow_html=True)

        names = [p['name'] for p in st.session_state.places]
        selected = st.selectbox("", names)
        selected_place = next(p for p in st.session_state.places if p['name'] == selected)
        st.session_state.selected_place = selected_place

        address = selected_place.get('formatted_address', '')
        rating = selected_place.get('rating', '')
        photo = get_place_photo_url(selected_place['photos'][0]['photo_reference'], google_key) if selected_place.get('photos') else ""
        lat, lng = get_lat_lng(address, google_key)

        st.markdown(f"### 🏞 관광지: {selected}")
        st.markdown("---")

        cols = st.columns([1.5, 1])
        with cols[0]:
            st.markdown(f"""
                <div style='font-size:18px; margin-bottom:10px;'>📍 <b>주소:</b> {address}</div>
                <div style='font-size:18px; margin-bottom:18px;'>⭐ <b>평점:</b> {rating}</div>
                <div style='margin-top:10px; margin-bottom:5px; font-size:17px; font-weight:bold;'>📝 사용자 리뷰</div>
            """, unsafe_allow_html=True)
            st.markdown(render_reviews(get_reviews(selected_place['place_id'], google_key, 3)), unsafe_allow_html=True)

        with cols[1]:
            if photo:
                st.image(photo, use_column_width=True)

        # 🔧 맛집 검색 반경 선택
        radius = st.slider("맛집 검색 반경 (미터)", min_value=500, max_value=3000, value=2000, step=100)

        restaurants = find_nearby_restaurants(lat, lng, google_key, radius=radius)
        df = pd.DataFrame(restaurants)
        df = preprocess_restaurant_data(df)

        display_top_restaurants(df)

        # 📂 CSV 다운로드
        csv = df.to_csv(index=False).encode('utf-8')
        st.download_button("📅 맛집 목록 CSV 다운로드", csv, f"{selected}_맛집목록.csv", "text/csv")

        st.markdown("---")
        st.subheader("🗺 지도에서 보기 (카카오맵)")

        places_js = ""
        for _, row in df.head(10).iterrows():
            if row["전화번호"] != "없음":
                search_key = row["전화번호"]
            else:
                search_key = f"{row['주소']} {row['이름']}"
            places_js += f'''
                {{
                    name: "{row["이름"]}",
                    address: "{row["주소"]}",
                    phone: "{row["전화번호"]}",
                    lat: {row["위도"]},
                    lng: {row["경도"]},
                    search_key: "{search_key}"
                }},
            '''

        html_code = f"""
        <html>
        <head>
            <meta charset="utf-8">
            <script src="//dapi.kakao.com/v2/maps/sdk.js?appkey={kakao_key}"></script>
        </head>
        <body>
            <div id="map" style="width:100%; height:500px;"></div>
            <script>
                var map = new kakao.maps.Map(document.getElementById('map'), {{
                    center: new kakao.maps.LatLng({lat}, {lng}),
                    level: 4
                }});

                var places = [{places_js}];

                places.forEach(function(p) {{
                    var marker = new kakao.maps.Marker({{
                        map: map,
                        position: new kakao.maps.LatLng(p.lat, p.lng)
                    }});

                    var infowindow = new kakao.maps.InfoWindow({{
                        content: "<div style='padding:5px; font-size:13px;'>" +
                                 p.name + "<br>" + p.address + "</div>"
                    }});
                    infowindow.open(map, marker);

                    kakao.maps.event.addListener(marker, 'click', function() {{
                        let kakaoUrl = "https://map.kakao.com/?q=" + encodeURIComponent(p.search_key);
                        window.open(kakaoUrl, "_blank");
                    }});
                }});
            </script>
        </body>
        </html>
        """
        components.html(html_code, height=550)

if __name__ == "__main__":
    main()