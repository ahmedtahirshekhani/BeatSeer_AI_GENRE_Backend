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

    df_f = pd.DataFrame()

    if artist_data['artists']['items']:
        artist_info = artist_data['artists']['items'][0]

        artist_details = {
            'artist_id': artist_info['id'],
            'name': artist_info['name'],
            'popularity': artist_info['popularity'],
            'genres': artist_info['genres'],
            'followers': artist_info['followers']['total'],
            'external_url': artist_info['external_urls']['spotify'],
            'image': artist_info['images'][0]['url'] if artist_info['images'] else None,
        }
        
        return artist_details
    else:
        return {"error": "Artist not found"}

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

# Test endpoint
@app.get("/")
def read_root():
    return {"message": "Hello, FastAPI!"}

@app.get("/artist-analysis")

def get_artist_analysis(
    artist: str = Query(...),
    # youTubeApiKey: str = Query(...),
    spotify_CLIENT_ID: str = Query(...),
    spotify_CLIENT_SECRET: str = Query(...)
    ):
    print("spotify_CLIENT_ID: ", spotify_CLIENT_ID)
    print("spotify_CLIENT_SECRET: ", spotify_CLIENT_SECRET)
    print("artist: ", artist)

    client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
    prompt = """
    You are an AI model tasked with providing the following information about genre analysis and media suitability. Respond strictly in JSON format.

    If genre is Unknown:
        Use the genre of {{artist_name}} from your knowledge.

    If genre not found:
        Use "Classic" as the genre.

    Now, provide insights and analysis for {{genre}} and {{artist_name}}:  

    1. Genre Popularity & Compatibility:  
    - Provide a score (1-100) for {{genre}}, assessing their popularity and alignment with mainstream music trends.  
    - Identify which genre {{artist_name}}'s music is most compatible with, rating the level of compatibility as LOW, MEDIUM, HIGH, or VERY HIGH.  
    - Include comparisons to potential genres.  

    2. Genre Evolution & Trends:  
    - Analyze how {{artist_name}}'s genre(s) have evolved over time.  
    - Highlight key trends and their impact on audience engagement and future growth.  

    3. Growth Indicators & Industry Position:  
    - What are the key indicators of growth for {{artist_name}} in the music industry?  
    - Compare {{artist_name}}'s popularity and fanbase growth with other artists in similar genres.  
    - Provide insights into their market position, including rankings in Bollywood, Hindi pop, and Sufi music, as well as their standing among international artists.  

    4. Best Uses in Media & Entertainment:  
    - Recommend the most suitable media applications for {{artist_name}}'s music:  
    - Films, documentaries, commercials, TV shows, or other formats.  
    - Identify the best scene types where their music excels:  
    - "Character development moments," "Emotional transitions," "Rural/small town settings," "Reflective montages."  
    - Explain its effectiveness in storytelling, character arcs, and emotional engagement.  

    5. Sound Elements & Distinctive Style:  
    - Describe the key musical elements that define {{genre}}.  
    - Instrumentation, vocal style, dynamic range, and signature features.  
    - Discuss how these elements contribute to mood and emotional depth in productions.  

    6. Technical & Placement Strategies:  
    - Provide insights into the technical aspects of production, including:  
    - Mixing for film scenes, edit points, and instrumental availability.  
    - Discuss how {{genre}}'s music can be used in:  
    - Foreground vs. background placements in film, TV, and advertisements.  
    - Evaluate placement strategies such as:  
    - "Perfect for character-driven narratives," "Strong fit for heartland stories," "Authentic backdrop for American lifestyle themes," "Ideal for emotional story arcs."  

    Objective:  
    Deliver a structured breakdown of {{artist_name}}'s genre(s) with insights on popularity, evolution, media application, and technical details, ensuring a clear perspective on their place in the industry and their impact on storytelling.  

    Your response should be a JSON object structured like this (Example):

    {
        "artist_origin": {
            "country": "Pakistan"
        },
        "genre_info": {
            "genre": "Alternative Country",
            "score": 85,
            "compatibility": "HIGH"
        },
        "genre_evolution": [
            "Strong roots in Alternative Country with modern production elements",
            "High potential for mainstream crossover while maintaining authenticity",
            "Genre compatibility suggests strong audience retention"
        ],
        "growth_indicators": [
            "Consistent upward trajectory predicted over 18 months.",
            "Strong appeal to both traditional and modern audiences",
            "Significant potential for festival circuit impact"
        ],
        "market_position": [
            "Atif Aslam is a top-tier artist in Bollywood and the Hindi Pop scene, with a strong international following.",
            "He has a prominent position among South Asian music artists globally."
        ],
        "genres": ["Drama", "Coming of Age", "Indie Film"],
        "sceneTypes": [
            "Character development moments",
            "Emotional transitions",
            "Rural/small town settings",
            "Reflective montages"
        ],
        "potentialGenres": ["Romance", "Road Trip", "Documentary"],
        "placementStrategies": [
            "Perfect for character-driven narratives",
            "Strong fit for heartland stories",
            "Authentic backdrop for American lifestyle themes",
            "Ideal for emotional story arcs"
        ],
        "best_uses": [
            "Pivotal character decisions",
            "Transitional sequences",
            "Emotional climax scenes",
            "Opening/closing sequences"
        ],
        "impact": [
            "Strong emotional resonance for heartfelt moments",
            "Authentic storytelling through musical narrative",
            "Effectively underscores character development"
        ],
        "sound_elements": [
            "Authentic Alternative Country instrumentation",
            "Clear vocal storytelling",
            "Strong melodic hooks for scene enhancement",
            "Versatile dynamic range"
        ],
        "technical_details": [
            "Clean mix suitable for dialogue overlay",
            "Multiple edit points for flexible scene timing",
            "Available instrumental versions recommended",
            "Suitable for both foreground and background placement"
        ]
    }
"""

    def get_claude(genre, artist_name, prompt=prompt):
      
        try:
            formatted_prompt = (
                prompt.replace("{{genre}}", genre)
                    .replace("{{artist_name}}", artist_name)
            )

            message = client.messages.create(
                model="claude-3-5-haiku-20241022",
                max_tokens=1500,
                temperature=0.7,
                system="You are an expert in music and genre analysis. Always return a valid JSON object, with no extra text.",
                messages=[{"role": "user", "content": formatted_prompt}]
            )
            return message
        except Exception as e:
            print("Error:", e)
            return None

    if spotify_CLIENT_ID and spotify_CLIENT_SECRET and artist:
        artist_origin = get_artist_country(artist)
        print("Artist Origin:", artist_origin)
        if artist_origin in ["RU", "CN"]:
            return {'artist_name': artist, 'analysis':{"artist_origin":{"message": "We cannot provide analysis for artists from Russia and China because of data restrictions."}}} 

        CLIENT_ID = spotify_CLIENT_ID
        CLIENT_SECRET = spotify_CLIENT_SECRET
        auth_manager = SpotifyClientCredentials(client_id=CLIENT_ID, client_secret=CLIENT_SECRET)
        sp = spotipy.Spotify(auth_manager=auth_manager)

        artist_details = fetch_artist_details(sp, artist)
        print("artist_details: ", artist_details)

        if "error" in artist_details:
            raise HTTPException(status_code=404, detail=artist_details["error"])

        artist_name = artist_details['name']
        popularity = artist_details['popularity']
        genre = artist_details['genres'][0] if artist_details['genres'] else None
        # print("Spotify Genre:", genre)

        if not genre:
            genres = fetch_genre_from_musicbrainz(artist_name)
            genre = genres[0] if genres else "Classic"
            # print("MusicBrainz Genre:", genre)

     
        response = get_claude(genre, artist_name)
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
