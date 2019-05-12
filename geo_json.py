import requests
import time
import subprocess

#==============================================================================#
#================== Convert KML geometry into GeoJSON dicts. ==================#
#==============================================================================#

#put each x,y coord pair in a 2-element list because JSON has no tuples
def pull_coords(tag):
    return [[float(t[0]),float(t[1])]
            for t in (triple.split(',')
                      for triple in tag.coordinates.string.strip().split())]

def as_geometry(poly_pt):
    result = {'type': poly_pt.name,
              'coordinates':[]}
    obi = poly_pt.outerBoundaryIs
    if obi:
        outer = pull_coords(obi)
        inners = [pull_coords(ibi) for ibi in poly_pt('innerBoundaryIs')]
        result['coordinates'] = [outer] + inners
    else:
        result['coordinates'] = [
                float(x)
                for x in poly_pt.coordinates.string.strip().split(',')][:2]
    return result

#Return a GeoJSON interpretation of an arbitrary kml soup.
#properties should be a function which accepts a Polygon or Point from inside a
#Placemark and which returns a dict of the properties for that Placemark or for
#that specific component of the Placemark.
def geojson(soup, properties=(lambda tag : {})):
    result = {
        'type': 'FeatureCollection',
        'features': []}
    for pm in soup("Placemark"):
        #GeoJSON does not natively support MultiGeometries so to account for
        #them we must include each constituent Polygon as its own top-level
        #Feature and keep them in-sync for styling by giving them the same
        #properties
        for feature in pm(['Polygon', 'Point']):
            feat = {'type':'Feature'}
            result['features'].append(feat)
            prop = properties(feature)
            if prop:
                feat['properties'] = prop
            feat['geometry'] = as_geometry(feature)
    return result






