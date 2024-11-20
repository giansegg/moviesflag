from flask import Flask, render_template, request, jsonify
import requests
import json
import time
import sqlite3
from datetime import datetime
import logging
from typing import Dict, Optional, List

# Configuración de logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
apikey = "cae89675"

class CacheDB:
    def __init__(self, db_path: str = "movies_cache.db"):
        self.db_path = db_path
        self.setup_database()
    
    def get_connection(self):
        return sqlite3.connect(self.db_path)
    
    def setup_database(self):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.executescript("""
                CREATE TABLE IF NOT EXISTS search_cache (
                    search_key TEXT PRIMARY KEY,
                    data TEXT,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
                );
                
                CREATE TABLE IF NOT EXISTS movie_cache (
                    imdb_id TEXT PRIMARY KEY,
                    data TEXT,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
                );
                
                CREATE TABLE IF NOT EXISTS flag_cache (
                    country_name TEXT PRIMARY KEY,
                    flag_url TEXT,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
                );
            """)

cache_db = CacheDB()

# Memoria Cache
container1 = {}  #  búsquedas
container2 = {}  #  detalles de películas
container3 = {}  #  flags

def get_cached_data(cache_type: str, key: str, max_age: int = 3600) -> Optional[Dict]:
    """Obtiene datos del caché (memoria + DB)"""

    if cache_type == 'search' and key in container1:
        return container1[key]
    elif cache_type == 'movie' and key in container2:
        return container2[key]
    elif cache_type == 'flag' and key in container3:
        return container3[key]
    

    table_name = f"{cache_type}_cache"
    key_field = 'search_key' if cache_type == 'search' else 'imdb_id' if cache_type == 'movie' else 'country_name'
    
    with cache_db.get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(f"""
            SELECT data, timestamp FROM {table_name}
            WHERE {key_field} = ? 
            AND datetime(timestamp) > datetime('now', '-' || ? || ' seconds')
        """, (key, max_age))
        
        result = cursor.fetchone()
        if result:
            data = json.loads(result[0])

            if cache_type == 'search':
                container1[key] = data
            elif cache_type == 'movie':
                container2[key] = data
            elif cache_type == 'flag':
                container3[key] = data
            return data
    return None

def save_to_cache(cache_type: str, key: str, data: Dict):
    """Guarda datos en caché (memoria + DB)"""

    if cache_type == 'search':
        container1[key] = data
    elif cache_type == 'movie':
        container2[key] = data
    elif cache_type == 'flag':
        container3[key] = data
    

    table_name = f"{cache_type}_cache"
    key_field = 'search_key' if cache_type == 'search' else 'imdb_id' if cache_type == 'movie' else 'country_name'
    
    with cache_db.get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(f"""
            INSERT OR REPLACE INTO {table_name} ({key_field}, data, timestamp)
            VALUES (?, ?, CURRENT_TIMESTAMP)
        """, (key, json.dumps(data)))

def searchfilms(search_text: str, page: int = 1) -> Dict:
    """Busca películas con caché"""
    cache_key = f"{search_text}_{page}"
    cached_data = get_cached_data('search', cache_key)
    if cached_data:
        logger.info(f"Cache hit for search: {cache_key}")
        return cached_data
    
    start_time = time.time()
    url = f"https://www.omdbapi.com/?s={search_text}&page={page}&apikey={apikey}"
    response = requests.get(url)
    if response.status_code == 200:
        data = response.json()
        save_to_cache('search', cache_key, data)
        logger.info(f"Time for searchfilms API call: {time.time() - start_time} seconds")
        return data
    logger.error("Failed to retrieve search results")
    return {"Search": []}

def getmoviedetails(movie: Dict) -> Dict:
    """Obtiene detalles de película con caché"""
    imdb_id = movie["imdbID"]
    cached_data = get_cached_data('movie', imdb_id)
    if cached_data:
        logger.info(f"Cache hit for movie: {imdb_id}")
        return cached_data
    
    url = f"https://www.omdbapi.com/?i={imdb_id}&apikey={apikey}"
    response = requests.get(url)
    if response.status_code == 200:
        data = response.json()
        save_to_cache('movie', imdb_id, data)
        return data
    logger.error(f"Failed to retrieve movie details for {imdb_id}")
    return {}

def get_country_flag(fullname: str) -> Optional[str]:
    """Obtiene bandera de país con caché"""
    cached_data = get_cached_data('flag', fullname)
    if cached_data:
        logger.info(f"Cache hit for flag: {fullname}")
        return cached_data.get('flag_url')
    
    url = f"https://restcountries.com/v3.1/name/{fullname}?fullText=true"
    response = requests.get(url)
    if response.status_code == 200:
        country_data = response.json()
        if country_data:
            flag_url = country_data[0].get("flags", {}).get("svg")
            if flag_url:
                save_to_cache('flag', fullname, {'flag_url': flag_url})
                return flag_url
    logger.error(f"Failed to retrieve flag for country: {fullname}")
    return None

def merge_data_with_flags(filter: str, page: int = 1) -> List[Dict]:
    """Combina datos de películas con banderas"""
    filmssearch = searchfilms(filter, page)
    if not filmssearch.get("Search"):
        return []
    
    moviesdetailswithflags = []
    for movie in filmssearch["Search"]:
        moviedetails = getmoviedetails(movie)
        if not moviedetails.get("Country"):
            continue
            
        countriesNames = moviedetails["Country"].split(",")
        countries = []
        for country in countriesNames:
            country = country.strip()
            flag = get_country_flag(country)
            countrywithflag = {
                "name": country,
                "flag": flag
            }
            countries.append(countrywithflag)
            
        moviewithflags = {
            "title": moviedetails["Title"],
            "year": moviedetails["Year"],
            "countries": countries
        }
        moviesdetailswithflags.append(moviewithflags)
    
    return moviesdetailswithflags

@app.route("/")
def index():
    filter = request.args.get("filter", "").upper()
    return render_template("index.html", movies=merge_data_with_flags(filter))

@app.route("/api/movies")
def api_movies():
    filter = request.args.get("filter", "")
    page = int(request.args.get("page", 1))
    return jsonify(merge_data_with_flags(filter, page=page))

@app.route("/cache/clear", methods=["POST"])
def clear_cache():
    """Endpoint para limpiar el caché"""
    try:
        with cache_db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.executescript("""
                DELETE FROM search_cache;
                DELETE FROM movie_cache;
                DELETE FROM flag_cache;
            """)
        container1.clear()
        container2.clear()
        container3.clear()
        return jsonify({"status": "success", "message": "Cache cleared successfully"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

if __name__ == "__main__":
    app.run(debug=True)