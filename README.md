# Route Mapper

## Instructions

Install:

```shell

python3 -m venv env
source venv/bin/activate
python3 -m pip install Flask simplekml folium fastkml pandas numpy folium gpxpy
python3 -m pip freeze > requirements.txt

```

Run: 

```shell
python map_server.py -input_kml alaska.kml
```