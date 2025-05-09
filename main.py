import spotipy
from spotipy.oauth2 import SpotifyClientCredentials
import pandas as pd
from bs4 import BeautifulSoup
from io import StringIO
from fastapi import FastAPI, Query, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import anthropic
import json
import musicbrainzngs
import os
import pylast
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  
    allow_credentials=True,
    allow_methods=["*"],  
    allow_headers=["*"],  
)


def fetch_artist_details(sp, artist_name: str):
    artist_data = sp.search(q=artist_name, type='artist', limit=1)
    
    if not artist_data['artists']['items']:
        return {"error": "Artist not found"}
    
    artist_info = artist_data['artists']['items'][0]
    artist_id = artist_info['id']
    
    top_tracks = sp.artist_top_tracks(artist_id)
    albums = sp.artist_albums(artist_id, album_type='album', limit=3)
    
    artist_details = {
        'artist_id': artist_id,
        'name': artist_info['name'],
        'popularity': artist_info['popularity'],
        'genres': artist_info['genres'],
        'followers': artist_info['followers']['total'],
        'external_url': artist_info['external_urls']['spotify'],
        'image': artist_info['images'][0]['url'] if artist_info['images'] else None,
        'top_tracks': [{
            'name': track['name'],
            'popularity': track['popularity'],
            'album': track['album']['name'],
            'release_date': track['album']['release_date']
        } for track in top_tracks['tracks'][:3]],  # Top 3 tracks
        'albums': [{
            'name': album['name'],
            'release_date': album['release_date'],
            'total_tracks': album['total_tracks']
        } for album in albums['items'][:3]]  # Top 3 albums
    }
    
    return artist_details

musicbrainzngs.set_useragent("BeetSeer_AI_Backend", "1.0", "ahmedtahir.developer@gmail.com")

# Function to get artist country
def get_artist_country(artist_name):
    try:
        result = musicbrainzngs.search_artists(artist=artist_name, limit=1)
        if 'artist-list' in result and len(result['artist-list']) > 0:
            return result['artist-list'][0].get('country', 'Unknown')
    except Exception as e:
        print(f"Error fetching country for {artist_name}: {e}")
    return 'Unknown'

def fetch_genre_from_musicbrainz(artist_name: str):
    print("Fetching genre from MusicBrainz for artist:", artist_name)
    try:
        result = musicbrainzngs.search_artists(artist=artist_name, limit=1)
        # print("Result:", result)
        if result['artist-list']:
            artist_info = result['artist-list'][0]
            if 'tag-list' in artist_info:
                genres = [tag['name'] for tag in artist_info['tag-list']]
                return genres
            else:
                return []
        else:
            return []
    except Exception as e:
        print("Error fetching genre from MusicBrainz:", e)
        return []

def setup_lastfm_client():
    API_KEY = os.getenv("LASTFM_API_KEY")
    API_SECRET = os.getenv("LASTFM_API_SECRET")
    return pylast.LastFMNetwork(api_key=API_KEY, api_secret=API_SECRET)

# Add this new function to fetch Last.fm data
def fetch_lastfm_artist_data(artist_name: str):
    # print("Fetching Last.fm data for artist:", artist_name)
    try:
        lastfm = setup_lastfm_client()
        artist = lastfm.get_artist(artist_name)
        
        data = {
            "listeners": artist.get_listener_count(),
            "playcount": artist.get_playcount(),
            "bio": artist.get_bio_summary(),
            "tags": [tag.item.get_name() for tag in artist.get_top_tags()[:5]],  # Top 5 tags
            "top_tracks": [
                {"name": track.item.get_name(), "playcount": track.weight}
                for track in artist.get_top_tracks(limit=3)  # Top 3 tracks
            ],
            "top_albums": [
                {"name": album.item.get_name(), "playcount": album.weight}
                for album in artist.get_top_albums(limit=2)  # Top 2 albums
            ]
        }
        # print("Last.fm Data:", data)
        return data
    except pylast.WSError as e:
        print(f"Last.fm Error: {e}")
        return None
    except Exception as e:
        print(f"Unexpected Last.fm error: {e}")
        return None

LASTFM_PROMPT_ADDITION = """
Last.fm Data for {{artist_name}}:
- Listener Count: {{lastfm.listeners}}
- Total Plays: {{lastfm.playcount}}
- Top Tags (Genres): {{lastfm.tags|join(', ')}}
- Similar Artists: {{lastfm.similar|join(', ')}}
- Top Tracks:
{% for track in lastfm.top_tracks %}
  - {{track.name}} ({{track.playcount}} plays)
{% endfor %}
"""

# Test endpoint
@app.get("/")
def read_root():
    return {"message": "Hello, FastAPI!"}

@app.get("/artist-analysis")

def get_artist_analysis(
    artist: str = Query(...),
    genre: str = Query(None),
    projected_growth: str = Query(None),
    genre_compatibility: str = Query(None),
    artist_country: str = Query(None),
    # youTubeApiKey: str = Query(...),
    spotify_CLIENT_ID: str = Query(...),
    spotify_CLIENT_SECRET: str = Query(...)
    ):
    print("spotify_CLIENT_ID: ", spotify_CLIENT_ID)
    print("spotify_CLIENT_SECRET: ", spotify_CLIENT_SECRET)
    print("artist: ", artist)

    client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
    prompt = """
    You are an AI music analyst specializing in comprehensive artist evaluations. Analyze the provided Spotify and Last.fm data and return a STRICTLY FORMATTED JSON response with ALL fields as arrays/lists.

    RULES:
    1. MUST return valid JSON with ALL values as arrays - even single items must be in arrays
    2. Use ONLY the following structure - no additional fields
    3. For empty data, return empty arrays []
    4. Never include markdown or code block syntax

    DATA SOURCES:
    - Spotify: {{spotify_data}}
    - Last.fm: {{lastfm_data}}

    ANALYSIS INSTRUCTIONS:

    If genre is Unknown:
        Use the most common tag from Last.fm ({{lastfm_data.tags|join(', ')}}) or your knowledge.
    If genre not found:
        Use "Classic" as the genre.

    Analysis Framework:

    1. Genre Popularity & Compatibility:
        - Consider Spotify popularity ({{spotify_data.popularity}}/100) with {{spotify_data.followers}} followers
        - Compare with Last.fm metrics: {{lastfm_data.listeners}} listeners and {{lastfm_data.playcount}} plays
        - Cross-reference genre tags: 
        • Spotify: {{spotify_data.genres|join(', ') if spotify_data.genres else 'None'}}
        • Last.fm: {{lastfm_data.tags|join(', ')}}
        - Provide compatibility score (1-100) and level (LOW/MEDIUM/HIGH/VERY HIGH)
        - Note similar artists from Last.fm: {{lastfm_data.similar|join(', ')}}

    2. Genre Evolution & Trends:
        - Analyze genre development using:
        • Spotify release dates (oldest: {{spotify_data.albums[-1].release_date}})
        • Last.fm play patterns (top tracks: {{lastfm_data.top_tracks[0].name}})
        - Identify audience shifts through Last.fm listener trends

    3. Growth Indicators:
        - Compare platform metrics:
        • Spotify followers vs Last.fm listeners ratio
        • Track popularity across platforms
        - Assess cross-platform appeal using similar artists

    4. Media Suitability:
        - Recommend applications based on:
        • Spotify audio features
        • Last.fm listener demographics
        - Highlight scene types considering:
        • Top tracks from both platforms
        • Genre characteristics from crowd-sourced tags

    5. Sound Analysis:
        - Describe style using:
        • Spotify instrumentation data
        • Last.fm user-generated tags
        - Identify signature elements from:
        • Most played tracks (Last.fm)
        • Top albums (Spotify)

    6. Technical Strategies:
        - Suggest placements based on:
        • Spotify's available instrumental versions
        • Last.fm's foreground/background play patterns
        - Optimize using:
        • Edit points from track durations
        • Emotional arcs from lyrical analysis

    RESPONSE TEMPLATE - MUST FOLLOW EXACTLY:
    {
        "genre_info": {
            "genre": ["pop"],  // Always array
            "score": [85],     // Always array
            "compatibility": ["HIGH"]  // Always array
        },
        "genre_evolution": [
            "Evolution statement 1",
            "Evolution statement 2"
        ],
        "growth_indicators": [
            "Indicator 1",
            "Indicator 2",
            "Indicator 3"
        ],
        "market_position": [
            "Position statement 1",
            "Position statement 2"
        ],
        "genres": [
            "Genre 1",
            "Genre 2",
            "Genre 3"
        ],
        "sceneTypes": [
            "Scene type 1",
            "Scene type 2",
            "Scene type 3",
            "Scene type 4"
        ],
        "potentialGenres": [
            "Alternative genre 1",
            "Alternative genre 2"
        ],
        "placementStrategies": [
            "Strategy 1",
            "Strategy 2",
            "Strategy 3",
            "Strategy 4"
        ],
        "best_uses": [
            "Use case 1",
            "Use case 2",
            "Use case 3"
        ],
        "impact_statements": [
            "Impact 1",
            "Impact 2"
        ],
        "sound_elements": [
            "Element 1",
            "Element 2",
            "Element 3",
            "Element 4"
        ],
        "technical_details": [
            "Feature 1",
            "Feature 2",
            "Feature 3",
            "Feature 4"
        ]
    }
"""
    prompt2 = """
    You are an AI music analyst specializing in comprehensive artist evaluations. Analyze the provided Spotify and Last.fm data and return a STRICTLY FORMATTED JSON response with ALL fields as arrays/lists.

    RULES:
    1. MUST return valid JSON with ALL values as arrays - even single items must be in arrays
    2. Use ONLY the following structure - no additional fields
    3. For empty data, return empty arrays []
    4. Never include markdown or code block syntax

    DATA SOURCES:
    - Spotify: {{spotify_data}}
    - Last.fm: {{lastfm_data}}
    - Genre: {{genre}}
    - Artist Name: {{artist_name}}
    - Projected Growth score: {{projected_growth}}
    - Genre Compatibility: {{genre_compatibility}}
    - Artist Country: {{artist_country}}


    Analysis Framework:

    1. Genre Popularity & Compatibility:
        - Consider Spotify popularity ({{spotify_data.popularity}}/100) with {{spotify_data.followers}} followers
        - Compare with Last.fm metrics: {{lastfm_data.listeners}} listeners and {{lastfm_data.playcount}} plays
        - Cross-reference genre tags: 
        • Spotify: {{spotify_data.genres|join(', ') if spotify_data.genres else 'None'}}
        • Last.fm: {{lastfm_data.tags|join(', ')}}
        - Note similar artists from Last.fm: {{lastfm_data.similar|join(', ')}}

    2. Genre Evolution & Trends:
        - Analyze genre development using:
        • Spotify release dates (oldest: {{spotify_data.albums[-1].release_date}})
        • Last.fm play patterns (top tracks: {{lastfm_data.top_tracks[0].name}})
        - Identify audience shifts through Last.fm listener trends

    3. Growth Indicators:
        - Compare platform metrics:
        • Spotify followers vs Last.fm listeners ratio
        • Track popularity across platforms
        - Assess cross-platform appeal using similar artists

    4. Media Suitability:
        - Recommend applications based on:
        • Spotify audio features
        • Last.fm listener demographics
        - Highlight scene types considering:
        • Top tracks from both platforms
        • Genre characteristics from crowd-sourced tags

    5. Sound Analysis:
        - Describe style using:
        • Spotify instrumentation data
        • Last.fm user-generated tags
        - Identify signature elements from:
        • Most played tracks (Last.fm)
        • Top albums (Spotify)

    6. Technical Strategies:
        - Suggest placements based on:
        • Spotify's available instrumental versions
        • Last.fm's foreground/background play patterns
        - Optimize using:
        • Edit points from track durations
        • Emotional arcs from lyrical analysis

    RESPONSE TEMPLATE - MUST FOLLOW EXACTLY:
    {
        "genre_info": {
            "genre": ["{{genre}}"],  // Always array
            "score": [{{projected_growth}}],     // Use projected growth score
            "compatibility": ["{{genre_compatibility}}"]  // use compatibility from above
        },
        "genre_evolution": [
            "Evolution statement 1",
            "Evolution statement 2"
        ],
        "growth_indicators": [
            "Indicator 1",
            "Indicator 2",
            "Indicator 3"
        ],
        "market_position": [
            "Position statement 1",
            "Position statement 2"
        ],
        "genres": [
            "Genre 1",
            "Genre 2",
            "Genre 3"
        ],
        "sceneTypes": [
            "Scene type 1",
            "Scene type 2",
            "Scene type 3",
            "Scene type 4"
        ],
        "potentialGenres": [
            "Alternative genre 1",
            "Alternative genre 2"
        ],
        "placementStrategies": [
            "Strategy 1",
            "Strategy 2",
            "Strategy 3",
            "Strategy 4"
        ],
        "best_uses": [
            "Use case 1",
            "Use case 2",
            "Use case 3"
        ],
        "impact_statements": [
            "Impact 1",
            "Impact 2"
        ],
        "sound_elements": [
            "Element 1",
            "Element 2",
            "Element 3",
            "Element 4"
        ],
        "technical_details": [
            "Feature 1",
            "Feature 2",
            "Feature 3",
            "Feature 4"
        ]
    }
"""
    def get_claude(spotify_data, lastfm_data, genre, artist_name, prompt=prompt):
        print(prompt)
        try:
            formatted_prompt = (
                prompt.replace("{{genre}}", genre)
                    .replace("{{artist_name}}", artist_name)
                    .replace("{{spotify_data}}", json.dumps(spotify_data, indent=2))
                    .replace("{{lastfm_data}}", json.dumps(lastfm_data, indent=2))
            )
            # print("Formatted Prompt:", formatted_prompt)

            message = client.messages.create(
                model="claude-3-5-haiku-20241022",
                max_tokens=2000,  # Increased for additional data
                temperature=0.7,
                system="You are an expert in music and genre analysis. Always return a valid JSON object, with no extra text.",
                messages=[{"role": "user", "content": formatted_prompt}]
            )
            return message
        except Exception as e:
            print("Error:", e)
            return None

    if spotify_CLIENT_ID and spotify_CLIENT_SECRET and artist:
        if artist_country is  None or artist_country=="null":
            artist_origin = get_artist_country(artist)
            print("Artist Origin:", artist_origin)
            if not artist_origin in ['US', 'CA', 'MX', 'GB', 'FR', 'DE', 'IT', 'ES', 'NL', 'BE', 'CH', 'AT', 'SE', 'NO', 'DK', 'FI', 'IE', 'PT', 'LU', 'IS']:
                return {'artist_name': artist, 'analysis': {"artist_origin": {"message": f"We cannot provide analysis for artists from {artist_origin}."}}} 
        else:
            prompt = prompt2
            prompt = prompt.replace("{{artist_country}}", artist_country)
            prompt = prompt.replace("{{projected_growth}}", projected_growth)
            prompt = prompt.replace("{{genre_compatibility}}", genre_compatibility)
            prompt = prompt.replace("{{artist_name}}", artist)
            prompt = prompt.replace("{{genre}}", genre)
            artist_origin = artist_country
        print("Artist Genre: ", genre)

        CLIENT_ID = spotify_CLIENT_ID
        CLIENT_SECRET = spotify_CLIENT_SECRET
        auth_manager = SpotifyClientCredentials(client_id=CLIENT_ID, client_secret=CLIENT_SECRET)
        sp = spotipy.Spotify(auth_manager=auth_manager)

        artist_details = fetch_artist_details(sp, artist)
        # print("artist_details: ", artist_details)

        if "error" in artist_details:
            raise HTTPException(status_code=404, detail=artist_details["error"])
        
        lastfm_data = fetch_lastfm_artist_data(artist)

        artist_name = artist
        # popularity = artist_details['popularity']
        if genre is None:
            genre = (artist_details['genres'][0] if artist_details['genres'] 
                else (fetch_genre_from_musicbrainz(artist_name)[0] 
                if fetch_genre_from_musicbrainz(artist_name) 
                else "Classic"))

        spotify_data = {
            'popularity': artist_details['popularity'],
            'followers': artist_details['followers'],
            'top_tracks': artist_details['top_tracks'],
            'albums': artist_details['albums']
        }
        response = get_claude(spotify_data, lastfm_data, genre, artist_name, prompt)
        # print("Response: ", response)

        try:
            response_text = response.content[0].text
            parsed_response = json.loads(response_text)  # Convert JSON string to dictionary
            parsed_response["artist_origin"] = {"country": artist_origin}
            return {"artist_name": artist_name, "analysis": parsed_response}

        except json.JSONDecodeError as e:
            print("Error decoding JSON response:", e)
            raise HTTPException(status_code=500, detail="Error decoding JSON response from Claude API")
        except Exception as e:
            print("Unexpected error:", e)
            raise HTTPException(status_code=500, detail="Unexpected error occurred")
        
    else:
        raise HTTPException(status_code=400, detail="API key is required")

# get_newsletter_data()
