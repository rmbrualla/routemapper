# -*- coding: utf-8 -*-

import numpy as np
import pandas as pd
import folium
import time
import gpxpy
import types
import copy
from branca.element import MacroElement, Template, Element, Figure
from flask import Flask, render_template, request, jsonify, make_response
import folium
import json
from absl import app
from absl import flags
import dataclasses
import route
import utils
import kml_parser
import os
import tempfile

FLAGS = flags.FLAGS

flags.DEFINE_string('input_gpx', None, 'Input gpx filename.')
flags.DEFINE_string('input_kml', None, 'Input kml filename.')

def load_gpx(gpx_file):
  with open(gpx_file) as f:
    return gpxpy.parse(f)

map_app = Flask(__name__)

route_map = route.RouteMap()


def maybe_return_js_code():
  ret_dict = {'status':'OK'}  
  js_code = route_map.pop_js_commands()
  if len(js_code) > 0:
    ret_dict['js_code'] = js_code
  return json.dumps(ret_dict)


@map_app.route('/')
def index():
  reload_data()
  return render_template('index.html')

@map_app.route('/label', methods=['POST'])
def label():
  route_map.set_activity_type(request.form['element'], request.form['params'])
  return maybe_return_js_code()

@map_app.route('/split', methods=['POST'])
def split():
  route_map.split_route(
    request.form['element'],
    route.LatLng(float(request.form['lat']), float(request.form['lng'])))
  return maybe_return_js_code()

@map_app.route('/edit', methods=['POST'])
def edit():
  route_map.edit_route(request.form['element'])
  return maybe_return_js_code()

@map_app.route('/endedit', methods=['POST'])
def endedit():
  route_map.end_edit_route(request.form['route_name'], json.loads(request.form['latlngs']))
  return maybe_return_js_code()

@map_app.route('/create_route', methods=['POST'])
def create_route():
  route_map.create_route()  
  return maybe_return_js_code()

@map_app.route('/end_create_route', methods=['POST'])
def end_create_route():
  route_map.end_create_route(json.loads(request.form['latlngs']))
  return maybe_return_js_code()


@map_app.route('/save', methods=['POST'])
def save():
  route_map.save(request.form['filename'], request.form['label_name'])
  return maybe_return_js_code()

@map_app.route('/info', methods=['POST'])
def info():
  route_map.info(
    request.form['element'],
    route.LatLng(float(request.form['lat']), float(request.form['lng'])))
  return maybe_return_js_code()


@map_app.route('/remove', methods=['POST'])
def remove():
  route_map.remove_route(request.form['element'])
  
  return maybe_return_js_code()

@map_app.route('/add_label', methods=['POST'])
def add_label():
  route_map.add_label(request.form['element'], request.form['label_name'])  
  return maybe_return_js_code()

@map_app.route('/remove_label', methods=['POST'])
def remove_label():
  route_map.remove_label(request.form['element'], request.form['label_name'])  
  return maybe_return_js_code()

@map_app.route('/simplify', methods=['POST'])
def simplify():
  route_map.simplify(request.form['element'])  
  return maybe_return_js_code()

@map_app.route('/stats', methods=['POST'])
def stats():
  route_map.stats(request.form['label_name'])  
  return maybe_return_js_code()

@map_app.route('/enable_highlight', methods=['POST'])
def enable_highlight():
  route_map.enable_highlight(request.form['label_name'])  
  return maybe_return_js_code()

@map_app.route('/disable_highlight', methods=['POST'])
def disable_highlight():
  route_map.enable_highlight('')  
  return maybe_return_js_code()

@map_app.route('/wayback', methods=['POST'])
def wayback():
  route_map.wayback()  
  return maybe_return_js_code()

@map_app.route('/update_info', methods=['POST'])
def update_info():
  route_map.update_info(
    request.form['route_name'],
    request.form['name'],
    request.form['description'],
    request.form['labels'])
  return maybe_return_js_code()


@map_app.route('/commit', methods=['POST'])
def commit():
  route_map.save(FLAGS.input_kml)
  cmd = f"git reset; git add {FLAGS.input_kml}; git commit -m \"[track update] {request.form['message']}\""
  os.system(cmd)
  return maybe_return_js_code()

@map_app.route('/all_stats', methods=['GET'])
def all_stats():
  num_subsections_per_section = [3, 3, 2, 4, 3, 5]
  activities = ['total', 'trail', 'offtrail', 'bush', 'road', 'paddle', 'crossing', 'float', 'unknown']

  csv_str = ",".join(["name"] + sum([[a + "_distance", a + "_segments"] for a in activities], [])) + "\n"
  for section_index, num_subsections in enumerate(num_subsections_per_section):
    for subsection_index in range(num_subsections):
      label = f"s{section_index+1}{chr(ord('a') + subsection_index)}"
      stats_dict = route_map.compute_stats(label)
      stats_items = [stats_dict.get(act, (0.0, 0.0)) for act in activities]
      stats_items_strs = sum([[f"{distance/1609.34:.2f}", f"{num_segments}"] 
                             for distance, num_segments in stats_items],[])
      csv_str += ",".join([label] + stats_items_strs) + "\n"
  output = make_response(csv_str)
  output.headers["Content-Disposition"] = "attachment; filename=section_stats.csv"
  output.headers["Content-type"] = "text/csv"
  return output

@map_app.route('/push', methods=['POST'])
def push():
  cmd = f"git push"
  os.system(cmd)
  return maybe_return_js_code()

@map_app.route('/pull', methods=['POST'])
def pull():
  cmd = f"git pull"
  os.system(cmd)
  return maybe_return_js_code()

@map_app.route('/upload_route', methods=['POST'])
def upload_route():
  kml_file = request.files['uploaded_kml_route']
  print(kml_file)

  with tempfile.TemporaryDirectory() as tmpdirname:
    kml_path = os.path.join(tmpdirname, 'import.kml')
    kml_file.save(kml_path)
    imported_routes = kml_parser.parse_kml(kml_path)

  for r in imported_routes:
    import_route(r)
    print(r.name)
  return maybe_return_js_code()



markers_visible = True
@map_app.route('/toggle_marker_visibility', methods=['POST'])
def toggle_marker_visibility():
  global markers_visible
  markers_visible = not markers_visible
  visibility_str = "visible" if markers_visible else "hidden"
  route_map._js_commands += f"""
$("path[fill!=\\"none\\"]").attr('visibility', '{visibility_str}');
"""
  return maybe_return_js_code()

def import_route(r, static=False):
  r = r.simplify(1.0)
  r.line_style.width = max(r.line_style.width, 5.0)
  for activity_type, color in route.activity_color.items():
    if color == r.line_style.color:
      r.activity_type = activity_type
  r.labels = []
  for name_token in r.name.split():
    if len(name_token) >= 2 and name_token[0] == '#':
      label = name_token[1:]
      if label not in r.labels:
        r.labels.append(label)
  if r.labels:
    name = r.name
    for l in r.labels:
      name = name.replace(f' #{l}', '')
    r.name = name
  route_map.add_route(r, static=static)

def reload_data():
  global route_map
  route_map = route.RouteMap()
  if FLAGS.input_gpx:
    gpx = load_gpx(FLAGS.input_gpx)
    for r in gpx.routes:
      route_map.add_route(route.Route(
          name=r.name,
          points=[route.LatLng(p.latitude, p.longitude) for p in r.points]), static=True)
      break
    for t in gpx.tracks:
      break
      for i, s in enumerate(t.segments):
        name = t.name
        if len(t.segments) > 1:
          name += f'_{i}'
        route_map.add_route(route.Route(
            name=name,
            points=[route.LatLng(p.latitude, p.longitude) for p in s.points]), static=True)
        break
      break
  elif FLAGS.input_kml:
    routes = kml_parser.parse_kml(FLAGS.input_kml)
    for r in routes:
      import_route(r, static=True)

  route_map.fit_bounds()

  with open('templates/map.html', 'w') as f:
    f.write(route_map.map()._repr_html_()) 

def main(argv):
  reload_data()
  map_app.run(debug=True)


if __name__ == '__main__':
  app.run(main)

