from fastkml import kml
from fastkml import styles
import collections

import route

def _kml_color_to_rgb(kml_color):
  if kml_color[0] == '#':
    kml_color = kml_color[1:]
  color = kml_color[2:] if len(kml_color) == 8 else kml_color
  return f'{color[-2:]}{color[2:4]}{color[:2]}'


def parse_kml(kml_file):
  with open(kml_file, 'rb') as f:
      doc=f.read()
  k = kml.KML()
  k.from_string(doc)

  nodes_to_process = collections.deque()
  styles_dict = {}
  routes = []

  def process_node(node):
    if isinstance(node, kml.KML):
      nodes_to_process.extend(node.features())
    elif isinstance(node, kml.Document):
      for style in node.styles():
        if style.id in styles_dict:
          raise ValueError(f'Conflict in style names: {style.id}')
        styles_dict[style.id] = style

      nodes_to_process.extend(node.features())
    elif isinstance(node, kml.Folder):
      nodes_to_process.extend(node.features())
    elif isinstance(node, kml.Placemark):
      if node.geometry.geom_type == 'LineString':
        # These are exported by my tool. Assume they use styleUrl
        style = styles_dict[node.styleUrl[1:]]
        line_style = route.LineStyle()
        for st  in style.styles():
          if type(st) is styles.LineStyle:
            line_style = route.LineStyle(_kml_color_to_rgb(st.color), max(st.width, 2.0))
        latlngs = [route.LatLng(c[1], c[0]) for c in node.geometry.coords]
        routes.append(route.Route(name=node.name, points=latlngs, description=node.description, line_style=line_style))
        
      elif node.geometry.geom_type == 'MultiLineString':
        # These are exported by GAIA gps.
        latlngs = sum([[route.LatLng(c[1], c[0]) for c in g.coords] for g in node.geometry.geoms], [])
        first_style = next(node.styles())
        line_style = route.LineStyle()
        for st  in first_style.styles():
          if type(st) is styles.LineStyle:
            line_style = route.LineStyle(_kml_color_to_rgb(st.color), max(st.width, 2.0))
        routes.append(route.Route(name=node.name, points=latlngs, description=node.description, line_style=line_style))
      elif node.geometry.geom_type == 'Point':
        # ignore
        pass
      else:
        raise ValueError(f'Unknown geometry: {node.geometry.geom_type}')
    else:
      raise ValueError(f'Unknown node: f{type(node)}')

  nodes_to_process.append(k)

  while nodes_to_process:
    process_node(nodes_to_process.pop())
  return routes