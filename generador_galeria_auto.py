import requests
import re
import zipfile
import io
import time
import json
import os
from xml.etree import ElementTree as ET
from PIL import Image
from io import BytesIO

# URL pública del KMZ exportado desde Google My Maps
KMZ_URL = "https://www.google.com/maps/d/kml?mid=1O8SvvCnUPVh4Hvk_mE4KHCdihdfSBzw"
CACHE_FILE = "geocode_cache.json"

# Cargar caché desde disco si existe
if os.path.exists(CACHE_FILE):
    with open(CACHE_FILE, "r", encoding="utf-8") as f:
        geocode_cache = json.load(f)
else:
    geocode_cache = {}

# Usar API de Nominatim para convertir coordenadas en dirección
def reverse_geocode(lat, lon):
    key = f"{lat},{lon}"
    if key in geocode_cache:
        return geocode_cache[key]

    url = "https://nominatim.openstreetmap.org/reverse"
    params = {
        "lat": lat,
        "lon": lon,
        "format": "jsonv2",
        "zoom": 18,
        "addressdetails": 1
    }
    headers = {"User-Agent": "GaleriaCrevillentBot/1.0"}
    try:
        response = requests.get(url, params=params, headers=headers)
        response.raise_for_status()
        data = response.json()
        addr = data.get("address", {})
        road = addr.get("road", "")
        # Usar 'town' o 'city' según disponibilidad
        town = addr.get("town") or addr.get("city") or ""
        if road and town:
            address = f"{road}, {town}"
        elif road:
            address = road
        elif town:
            address = town
        else:
            address = "Dirección desconocida"
        geocode_cache[key] = address
        time.sleep(1)  # para evitar sobrecargar el servicio
        return address
    except Exception:
        return "Dirección desconocida"

# Descargar y extraer el archivo KML desde un KMZ
def download_kml_from_kmz(url):
    response = requests.get(url)
    response.raise_for_status()
    with zipfile.ZipFile(io.BytesIO(response.content)) as zf:
        for name in zf.namelist():
            if name.endswith(".kml"):
                kml_content = zf.read(name).decode("utf-8", errors="replace")
                # Guardar el archivo KML en el directorio de trabajo
                with open("archivo_descargado.kml", "w", encoding="utf-8") as f:
                    f.write(kml_content)
                return kml_content
    raise ValueError("No se encontró ningún archivo .kml en el KMZ")

# Extraer datos de cada marcador: nombre, coordenadas, imagen, dirección
def extract_markers(kml_content):
    ns = {"kml": "http://www.opengis.net/kml/2.2"}
    try:
        root = ET.fromstring(kml_content)
    except ET.ParseError as e:
        print(f"Error al parsear el KML: {e}")
        return []

    markers = []
    nuevos = 0
    for placemark in root.findall(".//kml:Placemark", ns):
        name = placemark.findtext("kml:name", default="", namespaces=ns)
        coords = placemark.findtext(".//kml:coordinates", default="", namespaces=ns)
        desc = placemark.find("kml:description", ns)
        desc_text = desc.text if desc is not None else ""
        # Filtrar todas las imágenes precedidas por <img src="
        image_urls = re.findall(r'<img src="(https?://[^"]+)"', desc_text)
        if coords:
            parts = coords.strip().split(',')
            if len(parts) >= 2:
                lon, lat = parts[0], parts[1]
                maps_link = f"https://www.google.com/maps/search/?api=1&query={lat},{lon}"
                key = f"{lat},{lon}"
                address = geocode_cache.get(key) or reverse_geocode(lat, lon)
                if key not in geocode_cache:
                    nuevos += 1
            else:
                maps_link = ""
                address = ""
        else:
            maps_link = ""
            address = ""
        for url in image_urls:
            markers.append({"name": name, "coordinates": coords.strip(), "url": url, "maps_link": maps_link, "address": address})

    print(f"Se encontraron {len(markers)} imágenes con datos. Nuevas direcciones geocodificadas: {nuevos}")
    return markers

# Generar archivo HTML con lightbox y navegación

def generate_html(markers, output_file="galeria_auto.html"):
    html = """
<!DOCTYPE html>
<html lang='es'>
<head>
    <meta charset='UTF-8'>
    <title>Galería de tapas</title>
    <style>
        body { font-family: sans-serif; padding: 20px; background: #f4f4f4; margin: 0; }
        h1 { text-align: center; margin: 40px 0; }
        .gallery { display: grid; grid-template-columns: repeat(auto-fit, minmax(500px, 1fr)); gap: 20px; }
        .item { background: white; border-radius: 10px; overflow: hidden; }
        .item img { width: 100%; height: auto; max-width: 1000px; display: block; cursor: pointer; }
        .caption { padding: 10px; text-align: center; font-size: 14px; color: #333; }
        .volver-mapa {
            position: absolute;
            top: 20px;
            left: 20px;
            background: #fff;
            color: #333;
            padding: 12px 24px;
            border-radius: 8px;
            text-decoration: none;
            font-weight: bold;
            box-shadow: 0 2px 8px rgba(0,0,0,0.15);
            z-index: 10;
            transition: background 0.2s;
        }
        .volver-mapa:hover {
            background: #f4f4f4;
        }
        #lightbox {
            position: fixed; top: 0; left: 0; width: 100%; height: 100%;
            background: rgba(0, 0, 0, 0.95); display: none;
            justify-content: center; align-items: center;
            flex-direction: column; z-index: 1000;
        }
        #lightbox img {
            width: 100%; /* Ajustar al ancho de la pantalla */
            height: auto; /* Mantener proporción */
            max-height: 90vh; /* Limitar altura máxima */
            object-fit: contain;
        }
        .nav-button {
            position: absolute; top: 50%; transform: translateY(-50%);
            background: rgba(255,255,255,0.2); color: white; font-size: 3em;
            border: none; padding: 10px 20px; cursor: pointer; z-index: 1001;
        }
        .nav-button:hover { background: rgba(255,255,255,0.4); }
        #prev { left: 10px; }
        #next { right: 10px; }
    </style>
</head>
<body>
    <a class="volver-mapa" href="index.html">&larr; Volver al mapa</a>
    <h1>Galería Automática<br>De tapes per Crevillent</h1>
    <div class='gallery'>
"""
    for i, marker in enumerate(markers):
        if marker.get("local_path"):
            html += f"""
            <div class='item'>
                <img src='{marker['local_path']}' alt='Imagen del mapa' onclick='openLightbox({i})'>
                <div class='caption'>
                    <strong>{marker['name']}</strong><br>
                    <a href='{marker['maps_link']}' target='_blank'>{marker['address']}</a>
                </div>
            </div>
            """

    html += """
    </div>
    <div id='lightbox' onclick='closeLightbox(event)'>
        <button class='nav-button' id='prev' onclick='prevImage(event)'>&#10094;</button>
        <img id='lightbox-img' src=''>
        <button class='nav-button' id='next' onclick='nextImage(event)'>&#10095;</button>
    </div>
    <script>
        const images = [
"""
    html += ",\n".join([f'"{m["local_path"]}"' for m in markers if m.get("local_path")]) + "];\n"
    html += """
        let currentIndex = 0;

        function openLightbox(index) {
            currentIndex = index;
            const lightbox = document.getElementById("lightbox");
            const img = document.getElementById("lightbox-img");
            img.src = images[currentIndex];
            lightbox.style.display = "flex";
        }

        function closeLightbox(e) {
            if (e.target.id === "lightbox" || e.target.tagName === "IMG") {
                document.getElementById("lightbox").style.display = "none";
            }
        }

        function prevImage(e) {
            e.stopPropagation();
            currentIndex = (currentIndex - 1 + images.length) % images.length;
            document.getElementById("lightbox-img").src = images[currentIndex];
        }

        function nextImage(e) {
            e.stopPropagation();
            currentIndex = (currentIndex + 1) % images.length;
            document.getElementById("lightbox-img").src = images[currentIndex];
        }
    </script>
</body>
</html>
"""
    with open(output_file, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"Galería generada: {output_file}")

    # Guardar caché en disco
    with open(CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(geocode_cache, f, ensure_ascii=False, indent=2)

# Descargar imágenes desde las URLs y guardarlas localmente
def download_images(markers, output_dir="imagenes"):
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)  # Crear el directorio si no existe

    for i, marker in enumerate(markers):
        url = marker["url"]
        image_filename = f"imagen_{i + 1}.jpg"
        image_path = os.path.join(output_dir, image_filename)
        # Usar ruta relativa con barra normal para HTML
        marker["local_path"] = f"{output_dir}/{image_filename}"

        if os.path.exists(image_path):
            print(f"Imagen ya existe, no se descarga: {image_path}")
            continue

        try:
            response = requests.get(url, stream=True)
            response.raise_for_status()
            
            # Abrir la imagen desde la respuesta
            img = Image.open(BytesIO(response.content))
            
            # Redimensionar la imagen si su ancho es mayor a 1000 píxeles
            if img.width > 1000:
                ratio = 1000 / img.width
                new_height = int(img.height * ratio)
                img = img.resize((1000, new_height), Image.LANCZOS)
            
            img.save(image_path, "JPEG", quality=85)
            print(f"Imagen descargada y redimensionada: {image_path}")

        except Exception as e:
            print(f"Error al descargar o procesar la imagen {url}: {e}")
            marker["local_path"] = None

if __name__ == "__main__":
    kml_data = download_kml_from_kmz(KMZ_URL)
    markers = extract_markers(kml_data)
    download_images(markers)  # Descargar las imágenes
    generate_html(markers)
