import json
import os
from flask import Flask, render_template_string

# Load API Key
GOOGLE_MAPS_API_KEY = "AIzaSyAitZe6CQ4U3PYlrWgQx0NyE0TW7AagUGE"

# Path to JSON file
ARQUIVO_JSON = "C:/Users/pulta/OneDrive/Área de Trabalho/Laura Fiusa/arquivos_processados/MATRICULA_5555.json"

app = Flask(__name__)

def carregar_dados_json(caminho):
    """Loads property data from JSON."""
    try:
        with open(caminho, "r", encoding="utf-8") as arquivo:
            dados = json.load(arquivo)
        return dados
    except Exception as e:
        print(f"❌ Error loading JSON: {e}")
        return None

# HTML Template with multiple polygons and markers for first coordinates
HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>Mapa da Propriedade</title>
    <script src="https://maps.googleapis.com/maps/api/js?key={{ api_key }}"></script>
    <script>
      function initMap() {
        const map = new google.maps.Map(document.getElementById("map"), {
          zoom: 8,  // Default zoom level
          center: { lat: 0, lng: 0 },  // Temporary center
        });

        const propertyPolygons = {{ coords|safe }};
        const bounds = new google.maps.LatLngBounds();

        propertyPolygons.forEach((polygonCoords, index) => {
          const polygon = new google.maps.Polygon({
            paths: polygonCoords,
            strokeColor: "#FF0000",
            strokeOpacity: 0.8,
            strokeWeight: 2,
            fillColor: "#FF0000",
            fillOpacity: 0.35,
            map: map
          });

          // Extend map bounds to fit this polygon
          polygonCoords.forEach(coord => bounds.extend(coord));

          // Add marker at first coordinate of each polygon
          const firstCoord = polygonCoords[0];
          new google.maps.Marker({
            position: firstCoord,
            map: map,
            title: `Área ${index + 1}`,
            label: `${index + 1}`
          });
        });

        // Adjust map view to fit all polygons
        map.fitBounds(bounds);
      }
    </script>
</head>
<body onload="initMap()">
    <h1>Mapa da Propriedade</h1>
    <div id="map" style="height: 500px; width: 100%;"></div>
</body>
</html>
"""

@app.route("/")
def index():
    dados = carregar_dados_json(ARQUIVO_JSON)
    
    if not dados or "coordenadas" not in dados:
        return "<h1>Erro: Dados da propriedade não encontrados.</h1>"

    # Convert JSON coordinates (lon, lat, alt) → (lat, lon) for ALL polygons
    all_polygons = [
        [{"lat": lat, "lng": lon} for lon, lat, _ in polygon] 
        for polygon in dados["coordenadas"]
    ]

    return render_template_string(HTML_TEMPLATE, 
                                  api_key=GOOGLE_MAPS_API_KEY, 
                                  coords=json.dumps(all_polygons))

if __name__ == "__main__":
    app.run(debug=True)
