
from typing import Sequence, Text
import dataclasses
import folium
import utils
import types
import numpy as np
import folium.plugins
import my_draw
import os
import simplekml
import copy
import gpxpy
import html

@dataclasses.dataclass
class LatLng:
  lat: float = 0.0
  lng: float = 0.0
  # elevation: float = 0.0

@dataclasses.dataclass
class LineStyle:
  color: Text = 'ffffff'
  width: float = 2.0

@dataclasses.dataclass
class Route:
  name: Text = "route"
  points: Sequence[LatLng] = ()
  labels: Sequence[Text] = ()
  description: Text = ''
  line_style: LineStyle = LineStyle()
  activity_type: Text = ""
  
  def points_as_list(self):
    return [[p.lat, p.lng] for p in self.points]
  
  def split(self, latlng: LatLng):
    def _closest_point_and_distance(a, b, query):
      b_from_a_length = np.linalg.norm(b-a)
      normalized_b_from_a = (b-a) / b_from_a_length 
      closest_point = np.clip((query-a).dot(normalized_b_from_a), 0, b_from_a_length)  * normalized_b_from_a + a
      distance = np.linalg.norm(query - closest_point)
      return closest_point, distance
    points = np.array(self.points_as_list())
    query = np.array([latlng.lat, latlng.lng])
    best = (1e9, None, None)
    for idx, (a, b) in enumerate(zip(points[:-1], points[1:])):
      closest_point, distance = _closest_point_and_distance(a, b, query)
      if distance < best[0]:
        best = (distance, closest_point, idx)
    closest_point = best[1]
    idx = best[2]
    r1 = copy.deepcopy(self)
    r1.points = self.points[:idx+1] + [LatLng(*closest_point.tolist())]
    r2 = copy.deepcopy(self)
    r2.points = [LatLng(*closest_point.tolist())] + self.points[idx+1:]
    
    return r1, r2
  
  def length(self):
    locs = [gpxpy.geo.Location(p.lat, p.lng) for p in self.points]
    return gpxpy.geo.length_2d(locs)
    
    
  def simplify(self):
    r = copy.deepcopy(self)
    locs = [gpxpy.geo.Location(p.lat, p.lng) for p in self.points]
    new_locs = gpxpy.geo.simplify_polyline(locs, max_distance=5.)
    
    print(len(locs), len(new_locs))
    r.points = [LatLng(l.latitude, l.longitude) for l in new_locs]
    return r

def create_route_nodes(r: Route):
  points = r.points_as_list()
  segment_node = folium.FeatureGroup(name="segment", control=False)
  polyline = folium.PolyLine(points, color=f'#{r.line_style.color}', weight=max(r.line_style.width, 3.0), opacity=1.0, bubbling_mouse_events=False).add_to(segment_node)
  utils.JavaScript(script="""
{{kwargs['polyline']}}.on('click', function(e) {
console.log(e.latlng, "{{kwargs['polyline']}}");
parent.$('#lat').val(e.latlng["lat"]);
parent.$('#lng').val(e.latlng["lng"]);
parent.$('#element').val("{{kwargs['polyline']}}");
action_type = parent.$('input[name="action"]:checked').val();
index = action_type.indexOf(':');
if (index >= 0) {
  parent.$('#params').val(action_type.substr(index+1));
  action_type = action_type.substr(0, index);
}
$.ajax({
    url: '/' + action_type,
    data: parent.$('form').serialize(),
    type: 'POST',
    success: function(response){
      response_dict = JSON.parse(response);
      console.log(response_dict);
      if ("js_code" in response_dict) {
        eval(response_dict["js_code"]);
      }
    },
    error: function(error){
      console.log(error);
    }
  });
});""",  args={'polyline': polyline.get_name()}).add_to(segment_node)

  start_marker_nodes = []
  end_marker_nodes = []

  end_marker_nodes.append(folium.vector_layers.CircleMarker(
      location=points[-1], radius=9, color='white', weight=1,
      fill_color='red', fill_opacity=1).add_to(segment_node))
  end_marker_nodes.append(folium.RegularPolygonMarker(
      location=points[-1], fill_color='white', fill_opacity=1, color='white', 
      number_of_sides=4, radius=3, rotation=45).add_to(segment_node))

  start_marker_nodes.append(folium.vector_layers.CircleMarker(
    location=points[0], radius=9, color='white',
    weight=1, fill_color='green', fill_opacity=1).add_to(segment_node))
  start_marker_nodes.append(folium.RegularPolygonMarker(
    location=points[0], fill_color='white', fill_opacity=1, 
    color='white', number_of_sides=3, radius=3, rotation=0).add_to(segment_node))
  return types.SimpleNamespace(segment_node=segment_node,
                               polyline=polyline,
                               end_marker_nodes=end_marker_nodes,
                               start_marker_nodes=start_marker_nodes)

activity_color = {
  "trail": "FFC900",
  "road": "6E7271",
  "offtrail": "FF6200",
  "bush": "7AD915",
  "paddle": "0479FF",
  "crossing": "5726C2",
  "float": "00DAE1",
}


class RouteMap:
    
  def __init__(self):
    self._route_dict = {}
    self._route_nodes_dict = {}
    self._js_commands = ''
    self._create_map()
    
  def _create_map(self):
    self._map = folium.Map(tiles=None, zoom_control=False, width="100%", height="75%",control_scale = True)
    # self._map.default_js.append(("draw", "https://cdnjs.cloudflare.com/ajax/libs/leaflet.draw/1.0.4/leaflet.draw.js"))
    # self._map.default_css.append(("draw", "https://cdnjs.cloudflare.com/ajax/libs/leaflet.draw/1.0.4/leaflet.draw.css"))
    folium.TileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}', attr='ArcGIS', name='World_Imagery').add_to(self._map)
    folium.TileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Topo_Map/MapServer/tile/{z}/{y}/{x}', attr='ArcGIS', name='Topo Map').add_to(self._map)
    folium.LayerControl(collapsed=False).add_to(self._map)
    self._draw = my_draw.Draw(
        export=False,
          position='topleft',
         draw_options={'polyline': {'allowIntersection': True}, 'polygon': False, 'rectangle': False, 'circle': False, 'circlemarker': False},
         edit_options={'poly': {'allowIntersection': True}}
    ).add_to(self._map)
#     utils.JavaScript(
# f"""
# // Initialise the FeatureGroup to store editable layers
# var drawnItems = new L.FeatureGroup();
# {self._map.get_name()}.addLayer(drawnItems);

# // Initialise the draw control and pass it the FeatureGroup of editable layers
# var drawControl = new L.Control.Draw({{
#   edit: {{
#     featureGroup: drawnItems
#   }}
# }});

# {self._map.get_name()}.addControl(drawControl);

# {self._map.get_name()}.on(L.Draw.Event.CREATED, function (e) {{
#   var type = e.layerType
#   var layer = e.layer;

#   // Do whatever else you need to. (save to db, add to map etc)

#   drawnItems.addLayer(layer);
# }});
# """).add_to(self._map)

    
  def add_route(self, route: Route, static=False):
    """Add route.
    
    If static = True, adds the nodes to the map directly instead
    of to the JS code var.
    """
    route_nodes = create_route_nodes(route)
    name = route_nodes.polyline.get_name()
    self._route_dict[name] = route
    self._route_nodes_dict[name] = route_nodes
    if static:
      route_nodes.segment_node.add_to(self._map)
    else:
      self._js_commands += utils.render_nodes(route_nodes.segment_node, self._map)
    return name
  
  def fit_bounds(self):
    points_array = np.concatenate([r.points_as_list() for _, r in self._route_dict.items()])
    self._map.fit_bounds([points_array.min(axis=0).tolist(), points_array.max(axis=0).tolist()]) 

  def map(self):
    return self._map

  def remove_route(self, route_name):
    segment_node = self._route_nodes_dict[route_name].segment_node
    self._js_commands += f"{self._map.get_name()}.removeLayer({segment_node.get_name()});\n"
    del self._route_dict[route_name]
    del self._route_nodes_dict[route_name]

  def set_activity_type(self, route_name, activity_type):
    r = self._route_dict[route_name]
    r.activity_type = activity_type
    r.line_style.color = activity_color[activity_type]
    self._js_commands += f"{route_name}.setStyle({{color: '#{r.line_style.color}'}});\n"
    
  def add_label(self, route_name, labels):
    r = self._route_dict[route_name]
    route_labels = set(r.labels)

    for label in labels.split(','):
      label = label.strip()
      if label not in r.labels:
        route_labels.add(label)
    r.labels = sorted(list(route_labels))
    if "primary" in r.labels:
      r.line_style.width = 4.5
      self._js_commands += f"{route_name}.setStyle({{weight: {r.line_style.width}}});\n"
    else:
      r.line_style.width = 3.0
      self._js_commands += f"{route_name}.setStyle({{weight: {r.line_style.width}}});\n"
    

  def remove_label(self, route_name, labels):
    r = self._route_dict[route_name]
    route_labels = set(r.labels)
    for label in labels.split(','):
      label = label.strip()
      if label in route_labels:
        route_labels.remove(label)
    r.labels = sorted(list(route_labels))
    if "primary" in r.labels:
      r.line_style.width = 4.5
      self._js_commands += f"{route_name}.setStyle({{weight: {r.line_style.width}}});\n"
    else:
      r.line_style.width = 3.0
      self._js_commands += f"{route_name}.setStyle({{weight: {r.line_style.width}}});\n"

    
  def split_route(self, route_name, latlng):
    route = self._route_dict[route_name]
    r1, r2 = route.split(latlng)
    self.remove_route(route_name)
    self.add_route(r1)
    self.add_route(r2)

  def pop_js_commands(self):
    js_commands = self._js_commands
    self._js_commands = ''
    return js_commands   
    
  def create_route(self):
    self._js_commands += f"""
C = $('iframe')[0].contentWindow;
C.{self._draw.get_name()}._toolbars['draw']._modes['polyline'].button.click();
"""

  def end_create_route(self, latlngs):
    r = Route(name='noname', points=[LatLng(p['lat'], p['lng']) for p in latlngs], description='')
    print(r)
    route_name = self.add_route(r)
    print(route_name)
    self._js_commands += f"""
console.log("{route_name}");
{route_name}.redraw();
"""
 
  def edit_route(self, route_name):
    self._js_commands += f"""
{route_name}.addTo(drawnItems);
{self._draw.get_name()}._toolbars['edit']._modes['edit'].button.click()
current_edit_line = {route_name};
current_route_name = "{route_name}";
"""

  def end_edit_route(self, route_name, latlngs):
    self._route_dict[route_name].points = [LatLng(p['lat'], p['lng']) for p in latlngs]
    return


  def simplify(self, route_name):
    r = self._route_dict[route_name]
    new_route = r.simplify()
    self.remove_route(route_name)
    self.add_route(new_route)

  
  def info(self, route_name, latlng):
    r = self._route_dict[route_name]
    description = r.description if r.description else ''
    length_in_m = r.length()
    length_str = f'{length_in_m/1000.0:.1f} km / {length_in_m*0.000621371:.1f} mi'
    labels_str = ' '.join(f'#{l}' for l in r.labels)
    self._js_commands += f"""
var popup = L.popup()
    .setLatLng({{lat: {latlng.lat}, lng: {latlng.lng}}})
    .setContent('<p><b>Name:</b> {html.escape(r.name)}<br /><b>Description:</b> {html.escape(description)}<br><b>Labels:</b> {html.escape(labels_str)}<br><b>Length:</b> {html.escape(length_str)}<br><b>Activity:</b> {r.activity_type} </p>')
    .openOn({self._map.get_name()});
"""
    return

  def stats(self, labels):
    labels = [l.strip() for l in labels.split(',')]
    stats_dict = {}  # (length_m, num_segments)
    for r in self._route_dict.values():
      all_labels_match = True
      for label in labels:
        if label not in r.labels:
          all_labels_match = False
      if all_labels_match:
        print(r.activity_type, len(r.activity_type))
        activity = r.activity_type if len(r.activity_type) > 0 else 'unknown'
        print(activity)
        current_stats = stats_dict.get(activity, (0.0, 0))
        stats_dict[activity] =  (current_stats[0] + r.length(), current_stats[1] + 1)
        current_stats = stats_dict.get('total', (0.0, 0))
        stats_dict['total'] =  (current_stats[0] + r.length(), current_stats[1] + 1)
    summary_str = ''
    activities = ['total', 'trail', 'offtrail', 'bush', 'road', 'paddle', 'crossing', 'float', 'unknown']
    for activity in activities:
      if activity not in stats_dict: continue
      length_m, num_segments = stats_dict[activity]
      summary_str += f"<b>{html.escape(activity)}</b>: {length_m/1000.0:.1f} km / {length_m*0.000621371:.1f} mi / {num_segments} segments <br>"
    labels_str = ' '.join(f'#{l}' for l in labels)
    self._js_commands += f"""
C = $('iframe')[0].contentWindow;
map = C.{self._map.get_name()};
bounds = map.getBounds();
latlng = {{lat: 0.5 * (bounds.getSouth() + bounds.getNorth()), lng: 0.5 * (bounds.getWest() + bounds.getEast())}};
var popup = C.L.popup()
    .setLatLng(latlng)
    .setContent('<p><h3>Stats</h3><b>Labels:</b> {html.escape(labels_str)}<br/>{summary_str}</p>')
    .openOn(C.{self._map.get_name()});
"""
    return

  def save(self, filename):
    print('save to filename', filename)
    if os.path.exists(filename):
      pass
      # self._js_commands += f"alert('File {filename} already exists, change filename.');"
      # return
    def _color_to_kml_color(color):
      return f'#ff{color[-2:]}{color[2:4]}{color[0:2]}'
    kml = simplekml.Kml()
    for r in self._route_dict.values():
      coords = [(c[1], c[0]) for c in r.points_as_list()]
      name = r.name + ' #'.join([''] + list(r.labels))
      line = kml.newlinestring(name=name, coords=coords, description=r.description)
      line.style.linestyle.color =  _color_to_kml_color(r.line_style.color) 
      line.style.linestyle.width = r.line_style.width
    kml.save(filename)

