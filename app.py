import os
import re
import requests
from bs4 import BeautifulSoup
from flask import Flask, render_template, request, jsonify

try:
    from serpapi import GoogleSearch
    HAS_SERPAPI = True
except ImportError:
    HAS_SERPAPI = False

app = Flask(__name__)

SERPAPI_KEY = "1a358c7694518a74b1245a23298fda753f44b449c9e8ea8f6ad12973da0865c0"

SHOPPING_DOMAINS = [
    'myntra.com', 'ajio.com', 'amazon.in', 'amazon.com', 'zara.com', 
    'hm.com', 'meesho.com', 'flipkart.com', 'nykaafashion.com', 
    'urbanic.com', 'shein.com', 'bewakoof.com', 'limeroad.com'
]

def extract_youtube_id(url):
    youtube_regex = (
        r'(https?://)?(www\.)?'
        r'(youtube\.com/watch\?v=|youtu\.be/|youtube\.com/shorts/)'
        r'([a-zA-Z0-9_-]{11})'
    )
    match = re.search(youtube_regex, url)
    return match.group(4) if match else None

def extract_urls(text):
    url_pattern = r'https?://[^\s<>"]+|www\.[^\s<>"]+'
    return re.findall(url_pattern, text)

def upload_image_to_public_url(file_path):
    """Local image ko direct public CDN URL me upload karta hai"""
    # Catbox.moe CDN
    try:
        with open(file_path, 'rb') as f:
            res = requests.post(
                'https://catbox.moe/user/api.php',
                data={'reqtype': 'fileupload'},
                files={'fileToUpload': f},
                timeout=12
            )
            if res.status_code == 200 and res.text.startswith('http'):
                cdn_url = res.text.strip()
                print(f"Direct Catbox CDN URL: {cdn_url}")
                return cdn_url
    except Exception as e:
        print("Catbox upload failed:", e)

    return None

def parse_youtube_video(video_url):
    video_id = extract_youtube_id(video_url)
    results = []
    
    if not video_id:
        try:
            headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
            resp = requests.get(video_url, headers=headers, timeout=5)
            soup = BeautifulSoup(resp.text, 'html.parser')
            urls = extract_urls(soup.get_text())
            
            for u in set(urls):
                if any(domain in u.lower() for domain in SHOPPING_DOMAINS):
                    results.append({
                        "title": "Extracted Shopping Link",
                        "store": u.split('/')[2].replace('www.', ''),
                        "url": u,
                        "source": "Web Page Content",
                        "confidence": "High"
                    })
        except Exception as e:
            print("Error parsing URL:", e)
        return results

    try:
        oembed_url = f"https://www.youtube.com/oembed?url=https://www.youtube.com/watch?v={video_id}&format=json"
        oembed_resp = requests.get(oembed_url, timeout=5).json()
        video_title = oembed_resp.get("title", "YouTube Video")
        channel_name = oembed_resp.get("author_name", "Creator")
        
        yt_page = f"https://www.youtube.com/watch?v={video_id}"
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
        page_resp = requests.get(yt_page, headers=headers, timeout=5)
        
        found_urls = extract_urls(page_resp.text)
        unique_links = set()
        
        for link in found_urls:
            clean_link = link.rstrip('.,;)"\'')
            if any(domain in clean_link.lower() for domain in SHOPPING_DOMAINS) or "dress" in clean_link.lower():
                if clean_link not in unique_links:
                    unique_links.add(clean_link)
                    store_name = "Online Store"
                    for domain in SHOPPING_DOMAINS:
                        if domain in clean_link.lower():
                            store_name = domain.split('.')[0].capitalize()
                            break

                    results.append({
                        "title": f"Outfit Link from {channel_name}",
                        "store": store_name,
                        "url": clean_link,
                        "source": "Video Description",
                        "confidence": "Direct Match"
                    })

        if not results:
            search_query = f"{video_title} dress buy online Myntra Ajio Amazon"
            results.append({
                "title": f"Find matching dress for: '{video_title}'",
                "store": "Google Shopping Search",
                "url": f"https://www.google.com/search?q={requests.utils.quote(search_query)}&tbm=shop",
                "source": "Shopping Search",
                "confidence": "Exact Keywords Match"
            })

    except Exception as e:
        print("YouTube parsing error:", e)

    return results


def search_dress_by_image(image_file):
    """Real Image Search using Google Lens API via SerpAPI"""
    results = []
    
    upload_dir = os.path.join(app.root_path, 'static', 'uploads')
    os.makedirs(upload_dir, exist_ok=True)
    file_path = os.path.join(upload_dir, image_file.filename)
    image_file.save(file_path)

    public_image_url = upload_image_to_public_url(file_path)

    if HAS_SERPAPI and SERPAPI_KEY and public_image_url:
        try:
            print(f"Scanning Google Lens for URL: {public_image_url}")
            params = {
                "engine": "google_lens",
                "url": public_image_url,
                "api_key": SERPAPI_KEY,
                "hl": "en",
                "gl": "in"
            }
            search = GoogleSearch(params)
            dict_results = search.get_dict()
            
            # Debugging Error Check
            if "error" in dict_results:
                print("SerpAPI Returned Error:", dict_results["error"])

            lens_results = dict_results.get("visual_matches", []) or dict_results.get("shopping_results", [])

            for match in lens_results[:6]:
                price_info = match.get("price", {})
                price_str = price_info.get("extracted_price") or price_info.get("value") or "Check Store"
                if isinstance(price_str, (int, float)):
                    currency = price_info.get("currency", "₹")
                    price_str = f"{currency}{price_str}"

                results.append({
                    "title": match.get("title", "Matching Dress Product"),
                    "store": match.get("source", "Online Store"),
                    "price": str(price_str),
                    "image": match.get("thumbnail", "https://images.unsplash.com/photo-1515886657613-9f3515b0c78f?auto=format&fit=crop&w=400&q=80"),
                    "url": match.get("link", "#"),
                    "confidence": "Exact Visual Match"
                })
            
            print(f"Found {len(results)} exact matches from Google Lens!")

        except Exception as e:
            print("SerpAPI Google Lens Error:", e)

    if not results:
        results.append({
            "title": "🔍 Search dress on Google Lens Live",
            "store": "Google Lens Search",
            "price": "Free Scan",
            "image": "https://images.unsplash.com/photo-1515886657613-9f3515b0c78f?auto=format&fit=crop&w=400&q=80",
            "url": f"https://lens.google.com/uploadbyurl?url={public_image_url}" if public_image_url else "https://lens.google.com/",
            "confidence": "Web Search"
        })

    return results


@app.route("/")
def index():
    return render_template("index.html")

@app.route("/api/scan-video", methods=["POST"])
def api_scan_video():
    data = request.json or {}
    video_url = data.get("url", "").strip()
    if not video_url:
        return jsonify({"error": "Please provide a valid video link"}), 400
    
    results = parse_youtube_video(video_url)
    return jsonify({"success": True, "results": results})

@app.route("/api/scan-image", methods=["POST"])
def api_scan_image():
    if 'image' not in request.files:
        return jsonify({"error": "No image uploaded"}), 400
    
    image_file = request.files['image']
    results = search_dress_by_image(image_file)
    return jsonify({"success": True, "results": results})

if __name__ == "__main__":
    print("Starting Didi's Dress Finder App on http://127.0.0.1:5000 ...")
    app.run(debug=True, port=5000)