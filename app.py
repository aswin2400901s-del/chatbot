from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel
from typing import Optional, List
from master_pipeline import smart_search
import uvicorn
from contextlib import asynccontextmanager
from fuzzy_match import _ensure_indexes
from NER_training import locality_list_norm

@asynccontextmanager
async def lifespan(app: FastAPI):
    _ensure_indexes(locality_list_norm)
    print("✅ Fuzzy match indexes ready")
    yield

app = FastAPI(title="Homes247 AI Search", lifespan=lifespan)
from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],   # tighten this in production
    allow_methods=["*"],
    allow_headers=["*"],
)

class SearchRequest(BaseModel):
    query: str
    search_type: Optional[str] = None  # "buy" | "rental" | "commercial" | "pg" | None = auto-detect

class BatchSearchRequest(BaseModel):
    queries: List[str]

# ---------------- POST endpoint for frontend ----------------
@app.post("/api/smart_search")
def smart_search_api(payload: SearchRequest):
    return JSONResponse(content=smart_search(payload.query, payload.search_type))

# ---------------- POST endpoint for external API usage ----------------
@app.post("/search")
def search_endpoint(payload: SearchRequest):
    """
    External API endpoint for property search.

    Supports all 4 search types. Pass optional "search_type" field:
      "buy" | "rental" | "commercial" | "pg"
    If omitted, type is auto-detected from the query text.

    Usage with Postman:
    - Method: POST
    - URL: http://localhost:8004/search
    - Headers: Content-Type: application/json
    - Body (raw JSON): {"query": "2bhk in whitefield under 50l"}
      or with explicit type: {"query": "boys pg under 8k"}

    Example Response (buy):
    {
        "bhk_numbers": 2,
        "bhkId": 2,
        "minPrice": 0,
        "maxPrice": 5000000,
        ...
    }
    Example Response (rental):
    {
        "bhk": "2 BHK",
        "furnishing": "Furnished",
        "tenantType": "Family",
        "maxRent": 25000,
        ...
    }
    """
    return JSONResponse(content=smart_search(payload.query, payload.search_type))

# -------- POST endpoint for multiple queries --------
@app.post("/api/batch_search")
def batch_search_api(payload: BatchSearchRequest):
    """
    Batch search API for multiple queries.

    Usage with Postman:
    - Method: POST
    - URL: http://localhost:8004/api/batch_search
    - Headers: Content-Type: application/json
    - Body (raw JSON):
      {
        "queries": [
          "2bhk in whitefield under 50l",
          "3bhk in indiranagar under 75l",
          "4bhk villa in bangalore"
        ]
      }

    Returns a list of SearchResponse objects for each query.
    """
    results = [smart_search(query) for query in payload.queries]
    return JSONResponse(content={"results": results})

# -------- POST endpoint for multiple BHK with same location --------
@app.post("/api/multi_bhk_search")
def multi_bhk_search_api(payload: SearchRequest):
    """
    Search with multiple BHK options.
    Extracts all BHK numbers and returns results for each.

    Usage with Postman:
    - Method: POST
    - URL: http://localhost:8004/api/multi_bhk_search
    - Headers: Content-Type: application/json
    - Body (raw JSON): {"query": "2bhk, 3bhk, 4bhk in whitefield under 50l"}

    Returns separate SearchResponse for each BHK variant.
    """
    import re

    query = payload.query
    base_query = re.sub(r'(\d+\s*bhk[,\s]*)+', '', query, flags=re.IGNORECASE).strip()

    # Extract all BHK numbers (e.g., "2bhk, 3bhk, 4bhk" → [2, 3, 4])
    bhk_matches = re.findall(r'(\d+)\s*bhk', query, re.IGNORECASE)

    if not bhk_matches:
        return JSONResponse(content={"results": [smart_search(query)]})

    # Generate queries for each BHK
    results = []
    for bhk in bhk_matches:
        modified_query = f"{bhk}bhk {base_query}"
        results.append(smart_search(modified_query))

    return JSONResponse(content={"results": results})


# ──────────────────────────────────────────────────────────────
# NEW: Autocomplete endpoint
# ──────────────────────────────────────────────────────────────
# @app.get("/api/autocomplete")
# def autocomplete(q: str = "", limit: int = 8):
#     """
#     Autocomplete endpoint — call on every keypress (debounced 250ms).

#     Usage:
#       GET /api/autocomplete?q=2bhk+in+white
#       GET /api/autocomplete?q=3bhk+flat+with+gym
#       GET /api/autocomplete?q=villa+under

#     Response:
#       {
#         "query": "2bhk in white",
#         "suggestions": [
#           {"label": "Whitefield", "value": "2bhk in Whitefield ", "type": "locality", "id": 1},
#           ...
#         ]
#       }

#     Trigger logic:
#       "in / near <text>"  → localities
#       "with <text>"       → amenities
#       "under / above"     → price hints
#       "sqft / area"       → area hints
#       "bhk"               → BHK options
#       "for <text>"        → property types
#       bare digit          → BHK suggestions
#       fallback            → top matching localities
#     """
#     suggestions = get_autocomplete_suggestions(q, limit=limit)
#     return {"query": q, "suggestions": suggestions}


# ---------------- Frontend HTML ----------------
@app.get("/", response_class=HTMLResponse)
async def get_frontend():
    html_content = """
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Homes247 AI Property Search</title>
        <style>
            * { margin: 0; padding: 0; box-sizing: border-box; }
            body {
                font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                min-height: 100vh;
                display: flex;
                justify-content: center;
                align-items: flex-start;
                padding: 30px 20px;
            }
            .container {
                background: white; border-radius: 20px;
                box-shadow: 0 20px 60px rgba(0,0,0,0.3);
                max-width: 950px; width: 100%; padding: 40px;
            }
            .header { text-align: center; margin-bottom: 24px; }
            .header h1 { color: #667eea; font-size: 2.2rem; margin-bottom: 8px; }
            .header p  { color: #666; font-size: 1rem; }

            /* ── Search box wrapper (position:relative for dropdown) ── */
            .search-box-wrapper { position: relative; margin-bottom: 12px; }
            .search-input-wrapper { display: flex; gap: 10px; }

            #queryInput {
                flex: 1; padding: 14px 18px;
                border: 2px solid #e0e0e0; border-radius: 10px;
                font-size: 1rem; transition: all 0.3s;
            }
            #queryInput:focus { outline: none; border-color: #667eea; box-shadow: 0 0 0 3px rgba(102,126,234,0.1); }
            #searchBtn {
                padding: 14px 36px;
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                color: white; border: none; border-radius: 10px;
                font-size: 1rem; font-weight: 600; cursor: pointer; transition: transform 0.2s;
            }
            #searchBtn:hover { transform: translateY(-2px); box-shadow: 0 5px 20px rgba(102,126,234,0.4); }
            #searchBtn:disabled { opacity: 0.6; cursor: not-allowed; transform: none; }

            /* ── Autocomplete Dropdown ── */
            #autocomplete-dropdown {
                position: absolute;
                top: calc(100% + 4px);
                left: 0;
                /* stop before the Search button */
                right: 130px;
                background: white;
                border: 1.5px solid #e0e0e0;
                border-radius: 12px;
                box-shadow: 0 8px 32px rgba(102,126,234,0.15);
                z-index: 999;
                overflow: hidden;
                display: none;   /* shown by JS when suggestions exist */
            }
            .ac-item {
                padding: 10px 16px;
                cursor: pointer;
                font-size: 0.9rem;
                border-bottom: 1px solid #f4f4f4;
                transition: background 0.15s;
                display: flex;
                align-items: center;
                gap: 8px;
                color: #333;
            }
            .ac-item:last-child { border-bottom: none; }
            .ac-item:hover { background: #f5f0ff; }
            .ac-badge {
                display: inline-block;
                padding: 2px 9px;
                border-radius: 10px;
                font-size: 0.68rem;
                font-weight: 700;
                text-transform: uppercase;
                letter-spacing: 0.4px;
                white-space: nowrap;
                flex-shrink: 0;
            }
            .ac-locality       { background: #e8f5e9; color: #2e7d32; }
            .ac-amenity        { background: #e3f2fd; color: #1565c0; }
            .ac-price          { background: #fff3e0; color: #e65100; }
            .ac-area           { background: #f3e5f5; color: #6a1b9a; }
            .ac-bhk            { background: #fce4ec; color: #880e4f; }
            .ac-property_type  { background: #e0f7fa; color: #006064; }
            .ac-city           { background: #ede7f6; color: #4527a0; }

            /* ── Example tags ── */
            .examples { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; }
            .example-tag {
                padding: 6px 14px; background: #f0f0f0;
                border-radius: 20px; font-size: 0.83rem;
                cursor: pointer; transition: background 0.2s;
            }
            .example-tag:hover { background: #e0e0ff; }

            /* ── Loading & Results ── */
            .loading { display: none; text-align: center; padding: 30px; }
            .spinner {
                width: 40px; height: 40px; border: 4px solid #f3f3f3;
                border-top: 4px solid #667eea; border-radius: 50%;
                animation: spin 1s linear infinite; margin: 0 auto;
            }
            @keyframes spin { 0%{transform:rotate(0deg)} 100%{transform:rotate(360deg)} }
            .results { display: none; margin-top: 20px; }
            .result-card { background: #f8f9fa; border-radius: 15px; padding: 25px; }
            .result-section h3 { color: #667eea; font-size: 1.1rem; margin-bottom: 12px; }
            .json-output {
                background: #2d2d2d; color: #f8f8f2; padding: 20px;
                border-radius: 10px; overflow-x: auto;
                font-family: 'Courier New', monospace;
                font-size: 0.92rem; line-height: 1.6;
                white-space: pre-wrap; word-wrap: break-word;
            }
            .type-badge {
                display: inline-block; padding: 3px 14px;
                border-radius: 20px; font-size: 0.78rem;
                font-weight: 700; margin-bottom: 10px; letter-spacing: 0.5px;
            }
            .badge-buy        { background: #e8f5e9; color: #2e7d32; }
            .badge-rental     { background: #e3f2fd; color: #1565c0; }
            .badge-commercial { background: #fff3e0; color: #e65100; }
            .badge-pg         { background: #f3e5f5; color: #6a1b9a; }
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>&#127968; Homes247 AI Search</h1>
                <p>Describe your property need in natural language</p>
            </div>

            <div class="search-box">
                <!-- Wrapper with position:relative so dropdown sits below input -->
                <div class="search-box-wrapper">
                    <div class="search-input-wrapper">
                        <input
                            type="text"
                            id="queryInput"
                            placeholder="E.g., 2bhk in whitefield under 50 lakhs"
                            autocomplete="off"
                        >
                        <button id="searchBtn" onclick="searchProperty()">Search</button>
                    </div>
                    <!-- Autocomplete dropdown rendered here by JS -->
                    <div id="autocomplete-dropdown"></div>
                </div>

                <div class="examples" id="examplesContainer"></div>
            </div>

            <div class="loading" id="loading">
                <div class="spinner"></div>
                <p style="margin-top:15px;color:#666;">Analyzing your query...</p>
            </div>
            <div class="results" id="results">
                <div class="result-card" id="resultCard"></div>
            </div>
        </div>

        <script>
            const EXAMPLES = [
                "2bhk in whitefield under 50l",
                "3bhk flat for rent under 30k",
                "office space for startup 3000 sqft"
            ];
            const BADGE_LABELS = { "buy":"BUY","rental":"RENTAL","commercial":"COMMERCIAL","pg":"PG / HOSTEL" };

            // ── Example tags ────────────────────────────────────────────
            function updateExamples() {
                const c = document.getElementById("examplesContainer");
                c.innerHTML = '<span style="font-size:0.83rem;color:#888;margin-right:6px;">Try:</span>';
                EXAMPLES.forEach(ex => {
                    const t = document.createElement("div");
                    t.className = "example-tag";
                    t.textContent = ex;
                    t.onclick = () => {
                        document.getElementById("queryInput").value = ex;
                        closeDropdown();
                    };
                    c.appendChild(t);
                });
            }

            // ── Autocomplete ─────────────────────────────────────────────
            let _acTimer = null;

            function closeDropdown() {
                const dd = document.getElementById("autocomplete-dropdown");
                dd.innerHTML = "";
                dd.style.display = "none";
            }

            function renderDropdown(suggestions) {
                const dd = document.getElementById("autocomplete-dropdown");
                dd.innerHTML = "";

                if (!suggestions || suggestions.length === 0) {
                    dd.style.display = "none";
                    return;
                }

                suggestions.forEach(s => {
                    const item = document.createElement("div");
                    item.className = "ac-item";
                    item.innerHTML =
                        '<span class="ac-badge ac-' + s.type + '">' + s.type + '</span>' +
                        '<span>' + s.label + '</span>';

                    item.onmousedown = (e) => {
                        // Use mousedown (fires before blur) so the click registers
                        e.preventDefault();
                        document.getElementById("queryInput").value = s.value;
                        closeDropdown();
                        searchProperty();
                    };

                    dd.appendChild(item);
                });

                dd.style.display = "block";
            }

            async function fetchSuggestions(q) {
                try {
                    const res = await fetch("/api/autocomplete?q=" + encodeURIComponent(q) + "&limit=8");
                    const data = await res.json();
                    renderDropdown(data.suggestions);
                } catch (err) {
                    console.error("Autocomplete error:", err);
                }
            }

            // ── Main search ──────────────────────────────────────────────
            async function searchProperty() {
                const query = document.getElementById("queryInput").value.trim();
                if (!query) { alert("Please enter a search query"); return; }

                closeDropdown();

                const loadingDiv = document.getElementById("loading");
                const resultsDiv = document.getElementById("results");
                const searchBtn  = document.getElementById("searchBtn");
                loadingDiv.style.display = "block";
                resultsDiv.style.display = "none";
                searchBtn.disabled = true;

                try {
                    const resp = await fetch("/api/smart_search", {
                        method: "POST",
                        headers: { "Content-Type": "application/json" },
                        body: JSON.stringify({ query })
                    });
                    const data = await resp.json();
                    const stype = data.search_type || "buy";
                    const label = BADGE_LABELS[stype] || stype.toUpperCase();
                    document.getElementById("resultCard").innerHTML =
                        '<div class="result-section">' +
                        '<span class="type-badge badge-' + stype + '">' + label + '</span>' +
                        '<h3>&#128203; Search Results (JSON)</h3>' +
                        '<pre class="json-output">' + JSON.stringify(data, null, 2) + '</pre>' +
                        '</div>';
                    resultsDiv.style.display = "block";
                } catch(err) {
                    console.error(err);
                    alert("An error occurred. Please try again.");
                } finally {
                    loadingDiv.style.display = "none";
                    searchBtn.disabled = false;
                }
            }

            // ── Event listeners ──────────────────────────────────────────
            document.addEventListener("DOMContentLoaded", () => {
                updateExamples();

                const input = document.getElementById("queryInput");

                // Enter key → search
                input.addEventListener("keydown", e => {
                    if (e.key === "Enter") { searchProperty(); return; }
                    // Escape → close dropdown
                    if (e.key === "Escape") { closeDropdown(); return; }
                });

                // Keyup → debounced autocomplete fetch
                input.addEventListener("input", () => {
                    clearTimeout(_acTimer);
                    const q = input.value;
                    if (!q.trim()) { closeDropdown(); return; }
                    _acTimer = setTimeout(() => fetchSuggestions(q), 250);
                });

                // Click outside → close dropdown
                document.addEventListener("click", e => {
                    if (!e.target.closest(".search-box-wrapper")) {
                        closeDropdown();
                    }
                });
            });
        </script>
    </body>
    </html>
    """
    return html_content


# ---------------- Run Server ----------------
if __name__ == "__main__":
    import socket

    def get_local_ip():
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            local_ip = s.getsockname()[0]
            s.close()
            return local_ip
        except Exception:
            return "Unable to detect"

    local_ip = get_local_ip()

    print("\n" + "="*60)
    print("🏠 Homes247 AI Search Server Starting...")
    print("="*60)
    print(f"\n📍 Access the application at:")
    print(f"   • Localhost:  http://localhost:8004")
    print(f"   • Local IP:   http://{local_ip}:8004")
    print(f"\n📡 API Endpoints:")
    print(f"   • POST: http://{local_ip}:8004/search")
    # print(f"   • GET:  http://{local_ip}:8004/api/autocomplete?q=2bhk+in+white")
    print(f"\n💡 Use the Local IP to access from other devices on your network")
    print("="*60 + "\n")

    uvicorn.run(
        "app:app",
        host="0.0.0.0",
        port=8004,
        reload=True
    )