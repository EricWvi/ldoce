from typing import Dict, Optional
from litestar import Litestar, get
from litestar.response import Response, File
from mdict.mdict_db import MdictDb
from word_utils import enhanced_word_lookup
import os
import sys


# Path to the LDOCE dictionary
LDOCE_PATH = "./dict/LongmanDictionaryOfContemporaryEnglish6thEnEn.mdx"

# Global database instance
mdict_db_instance: Optional[MdictDb] = None

# HTML wrapper template for dictionary entries
HTML_WRAPPER = '''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>LDOCE - {word}</title>
    <script>
        function playAudio(element, audioUrl) {{
            // Check if audio element already exists
            let audio = element.querySelector('audio');
            if (!audio) {{
                // Create new audio element
                audio = document.createElement('audio');
                audio.style.display = 'none';
                const source = document.createElement('source');
                source.src = audioUrl;
                source.type = 'audio/mpeg';
                audio.appendChild(source);
                element.appendChild(audio);
            }}
            
            // Play the audio
            audio.play().catch(function(error) {{
                console.error('Error playing audio:', error);
            }});
        }}
    </script>
</head>
<body>
    <div class="header">
        <img src="/static/ldoce-logo.svg" alt="LDOCE Logo" style="height:40px; vertical-align: middle;">
    </div>
    <div class="dictionary-entry">
        {content}
    </div>
</body>
</html>'''


async def startup_handler() -> None:
    """Initialize database on server startup"""
    global mdict_db_instance
    if not os.path.exists(LDOCE_PATH):
        print(f"Error: Dictionary not found at {LDOCE_PATH}")
        sys.exit(1)
    
    print(f"Initializing database with dictionary: {LDOCE_PATH}")
    mdict_db_instance = MdictDb(LDOCE_PATH)
    print("Database initialized")


async def shutdown_handler() -> None:
    """Clean up database on server shutdown"""
    print("Server shutting down")


@get(path="/health")
async def health_check() -> Dict[str, str]:
    return {"status": "healthy"}



def rewrite_resource_urls(html_content: str) -> str:
    """Rewrite resource URLs in HTML content before serving"""
    import re
    
    # Convert sound:// links to lazy-loaded audio with image controls
    def replace_sound_link(match):
        sound_url = match.group(1)
        img_content = match.group(2)
        api_url = f"/api/sound/{sound_url}"
        # Rewrite image sources in the img content
        img_content = img_content.replace('src="img/', 'src="/api/img/')
        return f'<span onclick="playAudio(this, \'{api_url}\')" style="cursor:pointer;" data-audio-url="{api_url}">{img_content}</span>'
    
    # Replace <a href="sound://..."><img ...></a> patterns
    html_content = re.sub(r'<a href="sound://([^"]+)"[^>]*>(<img[^>]*>)</a>', replace_sound_link, html_content)
    
    return (html_content
            .replace('src="img/', 'src="/api/img/')
            # .replace('entry://#', '#')
            .replace('href="/#', 'href="#')
            .replace('href="LongmanDictionaryOfContemporaryEnglish6thEnEn.css"', 'href="/static/LongmanDictionaryOfContemporaryEnglish6thEnEn.css"')
            .replace('src="LongmanDictionaryOfContemporaryEnglish6thEnEn.js"', 'src="/static/LongmanDictionaryOfContemporaryEnglish6thEnEn.js"'))


@get(path="/word/{word:str}")
async def get_word_definition(word: str) -> Response:
    """Get word definition as complete HTML page"""
    global mdict_db_instance
    if mdict_db_instance is None:
        error_content = "<p>Dictionary not initialized</p>"
        html = HTML_WRAPPER.format(word=word, content=error_content)
        return Response(content=html, media_type="text/html", status_code=500)
    
    try:
        results = enhanced_word_lookup(mdict_db_instance, word)
        if not results:
            content = f"<p>No definition found for '{word}'</p>"
        else:
            content = rewrite_resource_urls(results[0])  # Rewrite URLs before serving
        
        html = HTML_WRAPPER.format(word=word, content=content)
        return Response(content=html, media_type="text/html")
    except Exception as e:
        error_content = f"<p>Error looking up '{word}': {str(e)}</p>"
        html = HTML_WRAPPER.format(word=word, content=error_content)
        return Response(content=html, media_type="text/html", status_code=500)


@get(path="/favicon.ico")
async def serve_favicon() -> File:
    """Serve favicon.ico from static directory"""
    file_path = "./static/favicon.ico"
    if not os.path.exists(file_path):
        raise ValueError("Favicon not found")
    return File(path=file_path, media_type="image/x-icon")


@get(path="/static/{filename:str}")
async def serve_static_files(filename: str) -> File:
    """Serve CSS and JS files from static directory"""
    file_path = f"./static/{filename}"
    if not os.path.exists(file_path):
        raise ValueError(f"File not found: {filename}")
    
    # Set appropriate content type
    if filename.endswith('.css'):
        media_type = "text/css"
    elif filename.endswith('.js'):
        media_type = "application/javascript"
    elif filename.endswith('.svg'):
        media_type = "image/svg+xml"
    else:
        media_type = "application/octet-stream"
    
    return File(path=file_path, media_type=media_type)


@get(path="/api/sound/{path:path}")
async def serve_sound_files(path: str) -> Response:
    """Serve audio files from MDD archive"""
    global mdict_db_instance
    if mdict_db_instance is None:
        return Response(content="Dictionary not initialized", status_code=500)
    
    try:
        # Convert forward slashes to backslashes for MDD lookup
        backslash_path = path.replace('/', '\\')
        results = mdict_db_instance.mdd_lookup(backslash_path)
        
        if not results:
            return Response(content="Audio file not found", status_code=404)
        
        audio_data = results[0]
        return Response(content=audio_data, media_type="audio/mpeg")
    except Exception as e:
        return Response(content=f"Error serving audio: {str(e)}", status_code=500)


@get(path="/api/img/{filename:str}")
async def serve_image_files(filename: str) -> Response:
    """Serve image files from MDD archive"""
    global mdict_db_instance
    if mdict_db_instance is None:
        return Response(content="Dictionary not initialized", status_code=500)
    
    try:
        # Convert forward slashes to backslashes for MDD lookup
        backslash_filename = filename.replace('/', '\\')
        results = mdict_db_instance.mdd_lookup(f"\\img\\{backslash_filename}")
        
        if not results:
            return Response(content="Image file not found", status_code=404)
        
        image_data = results[0]
        
        # Determine content type based on file extension
        if filename.endswith('.png'):
            media_type = "image/png"
        elif filename.endswith('.jpg') or filename.endswith('.jpeg'):
            media_type = "image/jpeg"
        elif filename.endswith('.gif'):
            media_type = "image/gif"
        else:
            media_type = "application/octet-stream"
        
        return Response(content=image_data, media_type=media_type)
    except Exception as e:
        return Response(content=f"Error serving image: {str(e)}", status_code=500)


app = Litestar(
    route_handlers=[health_check, get_word_definition, serve_favicon, serve_static_files, serve_sound_files, serve_image_files],
    on_startup=[startup_handler],
    on_shutdown=[shutdown_handler],
)


def main():
    """Main function to run the server"""
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)


if __name__ == "__main__":
    main()
