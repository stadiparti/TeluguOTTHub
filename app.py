from flask import Flask, render_template, jsonify
import requests
from bs4 import BeautifulSoup
import csv
import os
from datetime import datetime, timedelta
import logging
import json
from dateutil import parser

app = Flask(__name__)
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')

OMDB_API_KEY = 'ffa36251'  # Replace with your actual OMDB API key
CSV_FILE = 'movie_data.csv'
SCRAPE_INTERVAL = timedelta(hours=24)  # Scrape every 24 hours

def scrape_ott_releases():
    logging.debug("Starting scrape_ott_releases")
    url = "https://trendraja.in/telugu-movie-ott-release-dates-2021/"
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    }

    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        soup = BeautifulSoup(response.content, 'html.parser')

        table = soup.find('table', {'id': 'tablepress-116'})

        if not table:
            logging.error("Table not found. The website structure might have changed.")
            return []

        movies = []
        rows = table.find_all('tr')

        logging.debug(f"Found {len(rows)} rows in the table")

        for i, row in enumerate(rows[1:], start=1):  # Skip header row
            columns = row.find_all('td')
            if len(columns) == 4:
                movie = {
                    'title': columns[0].text.strip(),
                    'release_date': columns[1].text.strip(),
                    'platform': columns[2].text.strip(),
                    'category': columns[3].text.strip()
                }
                movies.append(movie)
                logging.debug(f"Processed movie {i}: {movie['title']}")
            else:
                logging.warning(f"Row {i} has unexpected number of columns: {len(columns)}")

        logging.debug(f"Scraped {len(movies)} movies")
        return movies

    except requests.RequestException as e:
        logging.error(f"Error fetching the web page: {e}")
        return []

def fetch_movie_data(title):
    logging.debug(f"Fetching movie data for '{title}'")
    url = f"http://www.omdbapi.com/?t={title}&apikey={OMDB_API_KEY}"
    try:
        response = requests.get(url)
        response.raise_for_status()
        data = response.json()
        if data.get('Response') == 'True':
            return {
                'imdb_id': data.get('imdbID', ''),
                'imdb_url': f"https://www.imdb.com/title/{data.get('imdbID', '')}/",
                'imdb_title': data.get('Title', ''),
                'imdb_year': data.get('Year', ''),
                'imdb_plot': data.get('Plot', ''),
                'imdb_director': data.get('Director', ''),
                'imdb_actors': data.get('Actors', ''),
                'imdb_rating': data.get('imdbRating', ''),
                'imdb_poster': data.get('Poster', ''),
                'last_updated': datetime.now().isoformat()
            }
    except requests.RequestException as e:
        logging.error(f"Error fetching movie data for '{title}': {e}")
    return None

def load_movie_data():
    if not os.path.exists(CSV_FILE):
        return {}
    
    movie_data = {}
    with open(CSV_FILE, 'r', newline='', encoding='utf-8') as file:
        reader = csv.DictReader(file)
        for row in reader:
            movie_data[row['title']] = row
    logging.debug(f"Loaded {len(movie_data)} movies from CSV")
    return movie_data

def save_movie_data(movie_data):
    fieldnames = ['title', 'release_date', 'platform', 'category', 'imdb_id', 'imdb_url', 'imdb_title', 'imdb_year', 'imdb_plot', 'imdb_director', 'imdb_actors', 'imdb_rating', 'imdb_poster', 'last_updated']
    logging.debug(f"Saving {len(movie_data)} movies to CSV")
    with open(CSV_FILE, 'w', newline='', encoding='utf-8') as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        for movie in movie_data.values():
            writer.writerow(movie)
    logging.debug(f"Saved {len(movie_data)} movies to CSV")

def update_movie_data(movies):
    logging.debug(f"Updating movie data for {len(movies)} movies")
    movie_data = load_movie_data()
    
    for movie in movies:
        title = movie['title']
        logging.debug(f"Processing movie: '{title}'")
        
        if title not in movie_data or 'imdb_id' not in movie_data[title]:
            imdb_data = fetch_movie_data(title)
            if imdb_data:
                logging.debug(f"Movie data fetched successfully for '{title}'")
                movie_data[title] = {**movie, **imdb_data}
            else:
                logging.warning(f"No movie data found for '{title}', using original data")
                movie_data[title] = movie
        else:
            logging.debug(f"Using existing data for '{title}'")
    
    save_movie_data(movie_data)
    return movie_data

def categorize_movies(movies):
    released_movies = []
    upcoming_movies = []
    featured_movies = []
    today = datetime.now().date()

    def parse_date(date_string):
        if date_string.lower() == 'soon':
            return None
        try:
            return parser.parse(date_string).date()
        except ValueError:
            logging.warning(f"Could not parse date: {date_string}")
            return None

    def parse_rating(rating):
        try:
            return float(rating)
        except ValueError:
            return 0.0  # Return 0.0 for 'N/A' or any non-numeric rating

    for movie in movies:
        release_date = movie['release_date']
        parsed_date = parse_date(release_date)
        
        if parsed_date is None:
            upcoming_movies.append(movie)
        elif parsed_date <= today:
            released_movies.append(movie)
        else:
            upcoming_movies.append(movie)

        # Select featured movies (e.g., movies with high IMDb ratings)
        rating = parse_rating(movie.get('imdb_rating', '0'))
        if rating >= 7.5:
            featured_movies.append(movie)

    # Sort released movies by date, most recent first
    released_movies.sort(key=lambda x: parse_date(x['release_date']) or datetime.min.date(), reverse=True)
    
    # Sort upcoming movies by date
    upcoming_movies.sort(key=lambda x: parse_date(x['release_date']) or datetime.max.date())

    # Limit featured movies to top 5
    featured_movies = sorted(featured_movies, key=lambda x: parse_rating(x.get('imdb_rating', '0')), reverse=True)[:5]

    return released_movies, upcoming_movies, featured_movies
@app.route('/')
def index():
    try:
        movies = scrape_ott_releases()
        movie_data = update_movie_data(movies)
        released_movies, upcoming_movies, featured_movies = categorize_movies(list(movie_data.values()))
        logging.debug(f"Categorized {len(released_movies)} released movies, {len(upcoming_movies)} upcoming movies, and {len(featured_movies)} featured movies")
        return render_template('index.html', released_movies=released_movies, upcoming_movies=upcoming_movies, featured_movies=featured_movies)
    except Exception as e:
        logging.error(f"Error in index route: {e}", exc_info=True)
        return "An error occurred. Please check the server logs.", 500
@app.route('/movie/<string:imdb_id>')
def movie_details(imdb_id):
    movie = next((m for m in movie_data.values() if m['imdb_id'] == imdb_id), None)
    if movie is None:
        return "Movie not found", 404
    return render_template('movie_details.html', movie=movie)
    
@app.route('/api/movies')
def api_movies():
    try:
        movies = scrape_ott_releases()
        movie_data = update_movie_data(movies)
        released_movies, upcoming_movies, featured_movies = categorize_movies(list(movie_data.values()))
        return jsonify({
            "released_movies": released_movies,
            "upcoming_movies": upcoming_movies,
            "featured_movies": featured_movies
        })
    except Exception as e:
        logging.error(f"Error in api/movies route: {e}")
        return jsonify({"error": "An error occurred"}), 500

if __name__ == '__main__':
    app.run(debug=True)
