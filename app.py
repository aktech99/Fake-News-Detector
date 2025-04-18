import streamlit as st
import requests
import google.generativeai as genai
from newspaper import Article
from bs4 import BeautifulSoup

# --- API KEYS ---
FACT_CHECK_API_KEY = "AIzaSyD11k1-GMTDun8Vh-OxV9bXBlY0d3lRmOk"
GEMINI_API_KEY = "AIzaSyAw1u_V1Kfb-p-aU68lbGEBkB_LNBQmao4"
NEWS_API_KEY = "9283e95345bf4fffbbb1c699c1d64f99"

genai.configure(api_key=GEMINI_API_KEY)
gemini_model = genai.GenerativeModel(model_name="models/gemini-1.5-flash")

# --- Google Fact Check Tools API ---
def fact_check_search(query):
    try:
        params = {"query": query, "key": FACT_CHECK_API_KEY}
        response = requests.get("https://factchecktools.googleapis.com/v1alpha1/claims:search", params=params)
        data = response.json()
        if "claims" not in data:
            return []
        results = []
        for claim in data["claims"]:
            text = claim.get("text", "No claim text available")
            review = claim.get("claimReview", [{}])[0]
            publisher = review.get("publisher", {}).get("name", "Unknown")
            rating = review.get("textualRating", "Unrated")
            url = review.get("url", "")
            results.append({
                "claim": text,
                "rating": rating,
                "publisher": publisher,
                "url": url,
            })
        return results
    except Exception as e:
        return [{"claim": f"Error: {str(e)}"}]

# --- NewsAPI Real-time Search ---
def search_newsapi(query, max_articles=3):
    url = "https://newsapi.org/v2/everything"
    params = {
        "q": query,
        "apiKey": NEWS_API_KEY,
        "sortBy": "publishedAt",
        "language": "en",
        "pageSize": max_articles
    }
    try:
        response = requests.get(url, params=params)
        return response.json().get("articles", [])
    except Exception as e:
        return []

# --- Extract Full Text from URL ---
def extract_full_article_text(url):
    try:
        article = Article(url)
        article.download()
        article.parse()
        return article.text
    except Exception as e:
        return f"Could not extract article text: {e}"

# --- Gemini with Full Article Context ---
def gemini_fact_check_with_articles(claim, articles):
    if not articles:
        return "No news context available."

    article_texts = "\n\n".join(
        [f"Title: {a['title']}\nFull Text: {extract_full_article_text(a['url'])}" for a in articles]
    )

    prompt = f"""
You are a fact-checking assistant.

Claim: "{claim}"

Below are full texts of recent related news articles:

{article_texts}

Based on the above sources, determine if the claim is:
- "Likely Real"
- "Likely Fake"
- "Unclear"

Then explain your reasoning in 1–2 lines.
"""
    try:
        response = gemini_model.generate_content(prompt)
        return response.text
    except Exception as e:
        return f"Error calling Gemini: {e}"

# --- WHO News Scraper ---
def fetch_who_articles(max_articles=2):
    try:
        url = "https://www.who.int/news-room/releases"
        headers = {"User-Agent": "Mozilla/5.0"}  # To avoid being blocked
        res = requests.get(url, headers=headers)
        soup = BeautifulSoup(res.text, "html.parser")
        articles = []

        links = soup.select("a.link-container")

        for link in links[:max_articles]:
            title = link.get_text(strip=True)
            href = link.get("href", "")
            full_url = "https://www.who.int" + href if href.startswith("/") else href

            article_res = requests.get(full_url, headers=headers)
            article_soup = BeautifulSoup(article_res.text, "html.parser")
            body = article_soup.select("div.sf-detail-body-wrapper p")

            content = "\n".join([p.get_text(strip=True) for p in body if p.text.strip()])
            articles.append({
                "title": title,
                "url": full_url,
                "content": content if content else "Content could not be extracted."
            })

        return articles if articles else [{"title": "No articles found.", "url": "", "content": ""}]
    except Exception as e:
        return [{"title": "Error fetching WHO news", "url": "", "content": str(e)}]

# --- Gemini Fallback with WHO Data ---
def gemini_fact_check_with_who(claim, who_articles):
    context = "\n\n".join([f"Title: {a['title']}\nContent: {a['content']}" for a in who_articles])
    
    prompt = f"""
You are a fact-checking assistant with access to verified public health releases from WHO.

Claim: "{claim}"

Below are recent official releases from the World Health Organization:

{context}

Based on this information, determine if the claim is:
- "Likely Real"
- "Likely Fake"
- "Unclear"

Then explain your reasoning in 1–2 lines.
"""
    try:
        response = gemini_model.generate_content(prompt)
        return response.text
    except Exception as e:
        return f"Error calling Gemini with WHO data: {e}"

# --- Streamlit UI ---
# ... (everything above remains unchanged)

# --- Streamlit UI ---
st.set_page_config(page_title="Fake News Detector", page_icon="🧠")
st.title("🧠 Fake News Detector")
st.markdown("Enter a news headline or article snippet below. We'll fact-check it using Google's database, NewsAPI, and official WHO sources.")

query = st.text_area("📰 Enter News Headline or Short Claim:", height=180)

if st.button("Verify News"):
    if not query.strip():
        st.warning("⚠️ Please enter some text first.")
    else:
        st.info("🔍 Checking with Google Fact Check API...")
        results = fact_check_search(query)
        source_used = "Google Fact Check API"

        if results:
            st.success("✅ Fact-check data found:")
            for r in results:
                st.markdown(f"**Claim:** {r['claim']}")
                st.markdown(f"- **Rating:** {r['rating']}")
                st.markdown(f"- **Publisher:** {r['publisher']}")
                if r["url"]:
                    st.markdown(f"[View Source]({r['url']})")
                st.markdown("---")
        else:
            st.info("📡 No Google fact-check found. Searching NewsAPI...")
            articles = search_newsapi(query)
            source_used = "NewsAPI"

            if articles:
                st.success("📰 Found related recent news articles:")
                for article in articles:
                    st.markdown(f"**{article['title']}**")
                    st.markdown(f"- **Source:** {article['source']['name']}")
                    st.markdown(f"- **Published At:** {article['publishedAt'][:10]}")
                    st.markdown(f"- [Read more]({article['url']})")
                    st.markdown("---")

                st.info("🧠 Reasoning with Gemini AI using full article content...")
                gemini_result = gemini_fact_check_with_articles(query, articles)
                if "fake" in gemini_result.lower():
                    st.error("🚨 Gemini Verdict: Likely Fake")
                elif "real" in gemini_result.lower():
                    st.success("✅ Gemini Verdict: Likely Real")
                elif "unclear" in gemini_result.lower():
                    st.warning("⚠️ Gemini Verdict: Unclear")
                else:
                    st.info("🤖 Gemini AI Response:")
                st.write(gemini_result)

            else:
                st.warning("⚠️ No news found in NewsAPI. Checking WHO’s official website...")
                who_articles = fetch_who_articles()
                source_used = "WHO Website"

                if who_articles:
                    st.success("🌐 Found recent WHO articles. Verifying with Gemini AI...")
                    who_result = gemini_fact_check_with_who(query, who_articles)
                    if "fake" in who_result.lower():
                        st.error("🚨 Gemini Verdict (from WHO): Likely Fake")
                    elif "real" in who_result.lower():
                        st.success("✅ Gemini Verdict (from WHO): Likely Real")
                    elif "unclear" in who_result.lower():
                        st.warning("⚠️ Gemini Verdict (from WHO): Unclear")
                    else:
                        st.info("🤖 Gemini AI Response (WHO context):")
                    st.write(who_result)
                else:
                    st.error("❌ Could not fetch WHO articles. Final verification unavailable.")
                    source_used = "None"

        # Summary footer
        st.markdown("---")
        st.markdown(f"🔎 **Last Verified Using**: `{source_used}`")
