import os
import streamlit as st
import requests
import re
import time
from fpdf import FPDF
import tempfile
from PIL import Image
from io import BytesIO
from selenium import webdriver
from bs4 import BeautifulSoup
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from langchain_groq import ChatGroq
from langchain_core.messages import SystemMessage, HumanMessage
import speech_recognition as sr
from email.mime.text import MIMEText
from dotenv import load_dotenv
import smtplib
import pyttsx3
import time
import pyttsx3
import plotly.express as px
import pandas as pd
import re
import os

# ---- Config / Keys ----
load_dotenv()  # reads .env locally
def get_groq_key() -> str:
    # Only use .env for local development
    return os.getenv("GROQ_API_KEY")

def get_llm():
    key = get_groq_key()
    if not key:
        st.error("GROQ_API_KEY is missing. Put it in .env (local) or st.secrets (cloud).")
        st.stop()
    return ChatGroq(
        api_key=key,                 # <-- REQUIRED
        temperature=0.7,
        model_name="llama3-8b-8192"
    )

llm = get_llm()
# Voice input capture
def capture_voice_input():
    recognizer = sr.Recognizer()
    with sr.Microphone() as source:
        st.info("🎤 Listening...")
        audio = recognizer.listen(source, timeout=5)
    try:
        query = recognizer.recognize_google(audio)
        return query
    except:
        st.error("Could not understand audio")
        return ""

# Voice synthesis
def generate_audio_summary(text, filename="summary.mp3"):
    engine = pyttsx3.init()
    engine.save_to_file(text, filename)
    engine.runAndWait()
    return filename

# User location

def get_user_location():
    try:
        data = requests.get("https://ipinfo.io/json").json()
        return data.get("city", "Unknown"), data.get("region", ""), data.get("country", "")
    except:
        return "Unknown", "", ""

# Filter

def filter_products(products, min_price, max_price, min_rating):
    filtered = []
    for p in products:
        try:
            price_match = re.search(r"\d[\d,]*", p["price"])
            price = int(price_match.group(0).replace(",", "")) if price_match else 0
            rating = float(p.get("rating", 4.0))
            if min_price <= price <= max_price and rating >= min_rating:
                p["rating"] = rating
                filtered.append(p)
        except:
            continue
    return filtered

# Export PDF
def export_products_to_pdf(products, fn="product_report.pdf"):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", size=12)
    pdf.cell(0, 10, "Product Comparison Report", ln=True, align="C")
    pdf.ln(5)

    for p in products:
        try:
            # Download image
            response = requests.get(p['img'], timeout=10)
            image = Image.open(BytesIO(response.content))

            # Save to temp file
            with tempfile.NamedTemporaryFile(delete=False, suffix=".jpg") as tmp:
                image.save(tmp.name)
                img_path = tmp.name

            # Resize image for fitting in PDF
            pdf.image(img_path, w=50)
        except:
            pass  # if image download fails, skip image

        # Format and encode text to avoid UnicodeEncodeError
        text = f"{p['name']}\nPrice: {p['price']}  Rating: {p['rating']}\nLink: {p['link']}\n"
        safe_text = text.encode('latin-1', 'replace').decode('latin-1')  # Replace non-Latin chars with '?'
        pdf.multi_cell(0, 10, safe_text)
        pdf.ln(2)



def fetch_amazon_products(query, max_results=10):
    options = Options()
    options.add_argument("--headless")
    options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")
    options.add_argument("--window-size=1920,1080")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("user-agent=Mozilla/5.0")
    
    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)

    try:
        url = f"https://www.amazon.in/s?k={query.replace(' ', '+')}"
        driver.get(url)
        time.sleep(5)  # Allow page to load

        # Scroll to bottom to load lazy content
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(2)

        products = []
        items = driver.find_elements(By.CSS_SELECTOR, "div.s-main-slot div[data-component-type='s-search-result']")

        for item in items[:max_results]:
            try:
                title = item.find_element(By.TAG_NAME, "h2").text.strip()
                link = item.find_element(By.TAG_NAME, "a").get_attribute("href")

                # Try to get price from different selectors
                try:
                    price_whole = item.find_element(By.CSS_SELECTOR, "span.a-price-whole").text.strip()
                    try:
                        price_fraction = item.find_element(By.CSS_SELECTOR, "span.a-price-fraction").text.strip()
                        price = f"₹{price_whole}.{price_fraction}"
                    except:
                        price = f"₹{price_whole}"
                except:
                    try:
                        price = item.find_element(By.CSS_SELECTOR, "span.a-offscreen").text.strip()
                    except:
                        price = "₹0"

                try:
                    img = item.find_element(By.CSS_SELECTOR, "img.s-image").get_attribute("src")
                except:
                    img = ""

                try:
                    rating = item.find_element(By.CSS_SELECTOR, "span.a-icon-alt").text.split()[0]
                except:
                    rating = "4.0"

                products.append({
                    "name": title,
                    "price": price,
                    "img": img,
                    "rating": rating,
                    "link": link
                })

            except Exception as e:
                print("Error parsing item:", e)
                continue

        return products
    finally:
        driver.quit()


        




# --- Page Config ---
st.set_page_config(page_title="🛍️ AI Shopping Assistant", layout="wide")
st.title("🛒 Amazon Product Finder")
st.markdown("Search Amazon products, filter by price & rating, and get AI recommendations!")

# --- User Inputs ---
if st.button("🎤 Use Voice"):
    voice_query = capture_voice_input()
    st.session_state["voice_query"] = voice_query
    st.success(f"You said: {voice_query}")
category = st.selectbox("Choose a category", [
    "", "Mobile Phones", "Laptops", "Tablets", "Headphones", "Smartwatches",
    "Doormats", "Dresses", "Shoes", "T-Shirts", "Watches",
    "Beauty & Personal Care", "Makeup", "Hair Care", "Skin Care", "Perfumes",
    "Home Decor", "Kitchen Appliances", "Cookware", "Cleaning Supplies",
    "Books", "Toys & Games", "Board Games", "Stationery",
    "Grocery & Essentials", "Snacks", "Health & Fitness", "Supplements"
])
related_add_ons = {
    "laptop": ["Laptop Bag", "Wireless Mouse", "Cooling Pad", "Laptop Stand"],
    "acer": ["Laptop Bag for Acer", "Acer Mouse", "Cooling Pad", "USB Hub"],
    "iphone": ["iPhone Case", "Screen Protector", "Lightning Cable", "AirPods"],
    "camera": ["Camera Tripod", "Extra SD Card", "Camera Bag", "Lens Cleaning Kit"],
    "headphones": ["Audio Splitter", "Headphone Stand", "Bluetooth Adapter"],
    "monitor": ["HDMI Cable", "Monitor Stand", "Screen Cleaner Kit"],
    "printer": ["Printer Ink", "A4 Paper", "USB Cable", "Power Cord"],
    "tablet": ["Tablet Cover", "Stylus", "Bluetooth Keyboard", "Screen Protector"],
    "smartwatch": ["Watch Strap", "Charging Cable", "Screen Guard"],
    "tv": ["Wall Mount", "Remote Cover", "HDMI Cable", "Soundbar"],
    "shoes": ["Shoe Polish", "Socks", "Shoe Deodorizer"],
    "books": ["Bookmarks", "Reading Light", "Book Stand"],

    # Additional categories
    "dress": ["Matching Accessories", "Fashion Tape", "Dress Cover Bag"],
    "t-shirt": ["Cap", "Wrist Band", "Jacket"],
    "toys": ["Battery Pack", "Toy Storage Box", "Cleaning Wipes"],
    "games": ["Gaming Controller", "Headset", "Gaming Chair"],
    "skins": ["Mobile Skins", "Laptop Skins", "Gaming Console Skins"],
    "skin care": ["Face Wash", "Moisturizer", "Sunscreen"],
    "grocery": ["Storage Containers", "Grocery Bags", "Measuring Cups"],
    "decorated": ["Wall Stickers", "Fairy Lights", "Photo Frames"],
    "kitchen appliances": ["Non-Stick Spray", "Cleaning Brush", "Measuring Spoon Set"],
    "refrigerator": ["Deodorizer", "Fridge Organizer", "Ice Tray"],
    "bike": ["Helmet", "Mobile Holder", "Air Pump"]
}

query = st.text_input("🔍 Enter product keyword", placeholder="e.g., under 1000", value=st.session_state.get("voice_query", ""))

if category:
    query = f"{category} {query}"

num_products = st.selectbox("How many products to fetch?", [6, 10, 20, 50, 100], index=1)
col1, col2, col3 = st.columns(3)

with col1:
    min_price = st.text_input("Min Price (₹)", value="0")
with col2:
    max_price = st.text_input("Max Price (₹)", value="5000")
with col3:
    min_rating = st.text_input("Min Rating (0.0 - 5.0)", value="4.0")

# Convert inputs safely
try:
    min_price = int(min_price)
except:
    min_price = 0

try:
    max_price = int(max_price)
except:
    max_price = 5000

try:
    min_rating = float(min_rating)
except:
    min_rating = 4.0

sort_by = st.radio("Sort products by:", ["Relevance", "Price: Low to High", "Rating: High to Low"])

# --- Fetch Products ---
if query.strip():
    with st.spinner("🔄 Fetching Amazon products..."):
        products = fetch_amazon_products(query, max_results=num_products)

    if not products:
        st.warning("No products found. Try different keywords.")
    else:
        # Filter
        filtered = filter_products(products, min_price, max_price, min_rating)

        # Sort
        if sort_by == "Price: Low to High":
            filtered.sort(key=lambda x: int(re.search(r"\d+", x['price'].replace(',', '')).group()))
        elif sort_by == "Rating: High to Low":
            filtered.sort(key=lambda x: float(x['rating']), reverse=True)

        if not filtered:
            st.warning("No products match the filters.")
        else:
            # Display Products
            for p in filtered:
                st.image(p["img"], width=120)
                st.markdown(f"<a href='{p['link']}' target='_blank'><b>{p['name']}</b></a>", unsafe_allow_html=True)
                st.markdown(f"💵 {p['price']} ⭐ {p['rating']}")
                st.write("---")

            # Export to PDF
            if st.button("📄 Export to PDF"):
                pdf_file = export_products_to_pdf(filtered)
                summary = "Here are the top Amazon product suggestions based on your filters."
                audio_file = generate_audio_summary(summary)
                with open(pdf_file, "rb") as f:
                    st.download_button("Download PDF", f, file_name=pdf_file, mime="application/pdf")
                with open(audio_file, "rb") as a:
                    st.download_button("Download Voice Summary", a, file_name=audio_file, mime="audio/mpeg")

            # AI Recommendation
            prod_list = "\n".join([f"{p['name']} at {p['price']}" for p in filtered])
            prompt = f"Recommend the best product from:\n{prod_list}"
            chat = [SystemMessage(content="You are a shopping expert."), HumanMessage(content=prompt)]

            with st.spinner("🤖 Getting AI suggestion..."):
                answer = llm(chat).content
            st.success("✅ AI Recommendation:")
            st.markdown(answer)
            
            # 🔊 Add TTS button
            if st.button("🔊 Read Recommendation"):
                engine = pyttsx3.init()
                engine.say(answer)
                
            matched_add_ons = []
            for key in related_add_ons:
                if key in answer.lower():
                    matched_add_ons.extend(related_add_ons[key])

            if matched_add_ons:
                st.subheader("🧩 Related Product Suggestions:")
                for addon in matched_add_ons:
                    st.markdown(f"- {addon}")

                # 🔍 Fetch Add-ons from Amazon
                with st.spinner("🛒 Fetching related products from Amazon..."):
                    for addon in matched_add_ons[:5]:  # Limit to 5 suggestions
                        addon_results = fetch_amazon_products(addon, max_results=1)
                        if addon_results:
                            for p in addon_results:
                                st.markdown(f"**{p['name']}**")
                                st.markdown(f"💰 Price: {p['price']}")
                                st.markdown(f"⭐ Rating: {p['rating']}")
                                st.markdown(f"[🔗 View Product]({p['link']})")
                                st.markdown("---")