# modules/coordinates_handler.py
import json
import math
import re
import matplotlib.pyplot as plt

def are_points_equal(p1, p2, tol=1e-3):
    """
    Retorna True se as coordenadas dos pontos p1 e p2 forem muito próximas
    (diferença menor que 'tol').
    """
    return (abs(p1[0] - p2[0]) < tol) and (abs(p1[1] - p2[1]) < tol)

def parse_quadrant(quadrant_str, base_angle):
    """
    Interpreta o quadrante (NE, SE, SW, NW) e retorna
    um ângulo absoluto em graus a partir do Norte (sentido horário).

    Exemplos:
      - parse_quadrant("NE", 52) -> ~52°  (N 52° E)
      - parse_quadrant("SE", 30) -> ~150° (S 30° E)
      - parse_quadrant("SW", 20) -> ~200° 
      - parse_quadrant("NW", 10) -> ~350° 

    Se não encontrar quadrante, retorna base_angle como se fosse NE por padrão.
    """
    quadrant_str = quadrant_str.upper()
    if "SE" == quadrant_str:
        return 180 - base_angle if base_angle <= 90 else 180.0
    elif "SW" == quadrant_str:
        return 180 + base_angle if base_angle <= 90 else 180.0
    elif "NW" == quadrant_str:
        return 360 - base_angle if base_angle <= 90 else 270.0
    elif "NE" == quadrant_str:
        return base_angle
    else:
        # Se não achou nada, assumimos "NE" por padrão
        return base_angle

def parse_direction(direction_str):
    """
    Extrai o ângulo (em graus decimais) e o quadrante de uma string de direção,
    independentemente da ordem em que aparecem.

    Exemplos:
       "52°00' NE"   -> (52.0, "NE")
       "NW 42°00'"   -> (42.0, "NW")
       "42°00'NW"    -> (42.0, "NW")
       "5° 00' NE-SW" -> (5.0, "NE")  (separando a parte com hífen)

    Retorna: (base_angle, quadrant)
    """
    direction_str = direction_str.strip()
    
    # Encontra todos os números (graus e minutos)
    numbers = re.findall(r'(\d+(?:[.,]\d+)?)', direction_str)
    if len(numbers) >= 2:
        deg = float(numbers[0])
        minutes = float(numbers[1].replace(",", "."))
        base_angle = deg + minutes / 60.0
    elif len(numbers) == 1:
        base_angle = float(numbers[0])
    else:
        base_angle = 0.0

    # Procura por sequências de letras representando quadrantes
    # O padrão captura "NE", "NW", "SE", "SW" ou até "NE-SW", etc.
    quadrants = re.findall(r'([NSEW]{2}(?:-[NSEW]{2})?)', direction_str.upper())
    if quadrants:
        quadrant = quadrants[0]
        # Se houver hífen, usamos somente a primeira parte (ex.: "NE-SW" -> "NE")
        if '-' in quadrant:
            quadrant = quadrant.split('-')[0]
    else:
        quadrant = "NE"  # padrão

    return base_angle, quadrant

def plot_property(data):
    """
    Lê o array de 'Boundaries', interpretando:
      - O primeiro segmento como ângulo absoluto (com quadrante).
      - Os próximos como deflexões (direita/esquerda).
    Plota o polígono resultante.
    """
    try:
        boundaries = data["Georreferencing_Description"]["Boundaries"]
    except KeyError:
        print("Erro: JSON não contém 'Georreferencing_Description' ou 'Boundaries'.")
        return
    
    vertices = [(0.0, 0.0)]
    labels = [boundaries[0]["Starting_Point"]]
    
    current_bearing = 0.0  # ângulo em graus (0 = norte, sentido horário)
    first_segment = True

    for idx, segment in enumerate(boundaries):
        # Extrai a distância (considera apenas o primeiro valor numérico)
        dist_str = segment["Distance"].split()[0].replace(",", ".")
        try:
            distance = float(dist_str)
        except ValueError:
            print(f"Erro ao converter distância '{dist_str}'.")
            distance = 0.0
        
        # Extrai a parte de direção usando a função parse_direction,
        # que trata a ordem (número e quadrante) independentemente de como foram escritos.
        base_angle, quadrant_part = parse_direction(segment["Direction"])
        
        # Verifica se na "Observation" há indicação de deflexão para direita ou esquerda.
        obs = segment.get("Observation", "").lower()
        deflete_direita = ("deflete à direita" in obs) or ("defletindo à direita" in obs)
        deflete_esquerda = ("deflete à esquerda" in obs) or ("defletindo à esquerda" in obs)

        if first_segment:
            # O 1º segmento é interpretado como ângulo absoluto (com base no quadrante)
            abs_bearing = parse_quadrant(quadrant_part, base_angle)
            current_bearing = abs_bearing
            first_segment = False
        else:
            # Para os demais, a 'base_angle' é interpretada como deflexão relativa.
            if deflete_direita:
                current_bearing += base_angle
            elif deflete_esquerda:
                current_bearing -= base_angle
            else:
                # Se não especificado, trata como deflexão à direita por padrão.
                current_bearing += base_angle
            
            # Se quiser aplicar algum ajuste adicional com base no quadrante fornecido,
            # pode inserir a lógica aqui. No momento, essa parte foi removida.

        # Normaliza o bearing entre 0 e 360 graus
        current_bearing = current_bearing % 360.0
        
        # Converte para radianos
        theta = math.radians(current_bearing)
        
        # Calcula o deslocamento
        dx = distance * math.sin(theta)
        dy = distance * math.cos(theta)
        
        # Atualiza o último vértice
        x_last, y_last = vertices[-1]
        new_vertex = (x_last + dx, y_last + dy)
        
        vertices.append(new_vertex)
        labels.append(segment["End_Point"])
    
    # Fecha o polígono se o último ponto coincide com o primeiro
    if boundaries[-1]["End_Point"] == boundaries[0]["Starting_Point"]:
        if not are_points_equal(vertices[0], vertices[-1]):
            vertices[-1] = vertices[0]
            labels[-1] = labels[0]
    else:
        if not are_points_equal(vertices[0], vertices[-1]):
            vertices.append(vertices[0])
            labels.append(labels[0])
    
    # Plot
    xs, ys = zip(*vertices)
    prop_name = data.get("Property_Name", "Imóvel Desconhecido")
    matricula = data.get("Matricula_Number", "")
    
    plt.figure(figsize=(8, 8))
    plt.plot(xs, ys, marker='o', linestyle='-', color='blue')
    plt.title(f"{prop_name} (Matrícula: {matricula})")
    plt.xlabel("Eixo X (m)")
    plt.ylabel("Eixo Y (m)")
    plt.grid(True)
    plt.axis("equal")
    
    for (x, y, lab) in zip(xs, ys, labels):
        plt.text(x, y, f" {lab}", fontsize=9, color='red')
    
    plt.show()

def plot_coordinates_file(file_path):
    """
    Lê um arquivo JSON a partir do caminho informado e plota os limites do imóvel
    interpretando rumos de forma relativa.
    """
    with open(file_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    plot_property(data)
